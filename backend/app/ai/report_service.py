"""Transient session-scoped reports and evidence, keyed by immutable snapshots."""
from collections import OrderedDict
from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
import secrets
import time

from app.ai.limits import UsageLimits
from app.ai.prompts import PROMPT_VERSION, REPORT_TASK, CHAT_TASK
from app.ai.schemas import ReportDraft, ChatDraft, Finding
from app.ai.safety import sanitize, check_question
from app.ai.validation import validate_findings, render_finding, validation_diagnostic, QUALITATIVE_WARNING
from app.ai.client import input_size
from app.ai.evidence import stable_snapshot_id, same_security
from app.ai.bindings import binding_catalog
from app.core.exceptions import ApiError
from app.providers.permitted_use import require_public_data
from sqlalchemy.engine import make_url


class ResearchService:
    def __init__(self, settings, assembler, client):
        self.settings, self.assembler, self.client = settings, assembler, client
        self.limits = UsageLimits(settings)
        self.reports, self.snapshots = OrderedDict(), OrderedDict()
        self.generating = set()
        self.private_values = [settings.openai_api_key, settings.fmp_api_key, settings.sec_user_agent, settings.database_url]
        self.private_values.append(make_url(settings.database_url).password or "")

    def status(self):
        configured = bool(self.settings.openai_api_key.strip() and self.settings.openai_model.strip())
        enabled = self.settings.ai_research_enabled
        message = ("AI research is ready." if enabled and configured else
                   "AI research is disabled in the server configuration." if not enabled else
                   "Configure an OpenAI API key and an explicitly approved model on the server.")
        return {"enabled": enabled, "configured": configured, "available": enabled and configured, "message": message,
                "limitations": ["Research uses dated provider evidence; missing financial inputs and provider restrictions remain unavailable.",
                                "Qualitative filing coverage is bounded and may be unavailable. AI interpretations require source review."]}

    def require_available(self):
        if not self.status()["available"]:
            raise ApiError("ai_not_configured", self.status()["message"], 503)

    async def close(self):
        self.reports.clear()
        self.snapshots.clear()
        await self.client.close()

    def _prune(self):
        now = time.monotonic()
        for collection in (self.reports, self.snapshots):
            for key in list(collection):
                if collection[key][0] <= now:
                    collection.pop(key)
            while len(collection) > 64:
                collection.popitem(last=False)

    async def _context(self, ticker, valuation, instrument_id=None, listing_id=None):
        scope = {key: value for key, value in (("instrument_id", instrument_id), ("listing_id", listing_id)) if value is not None}
        # Privacy/licensing classification is validated before sanitization or
        # export; stripping a private source label cannot authorize transmission.
        package = require_public_data(await self.assembler.assemble(ticker, valuation, **scope))
        package = sanitize(package, self.private_values)
        if package["ticker"] != ticker:
            raise ApiError("ai_identity_mismatch", "The research evidence does not match this company.", 502)
        identity = package.get("identity")
        if instrument_id is not None and (not identity or identity.get("instrument_id") != instrument_id):
            raise ApiError("ai_identity_mismatch", "The research evidence does not match the selected instrument.", 502)
        if listing_id is not None and (not identity or identity.get("listing_id") != listing_id):
            raise ApiError("ai_identity_mismatch", "The research evidence does not match the selected listing.", 502)
        for item in package["registry"].values():
            selected = item.get("identity")
            if (bool(identity) != bool(selected) or identity and not same_security(identity, selected)):
                raise ApiError("ai_identity_mismatch", "The research evidence contains incompatible security identities.", 502)
        # The fixed methodology entry supports conceptual answers without recalled facts.
        method = {"category": "historical_metric", "provider": "Fairworth", "title": "Deterministic valuation methodology",
                  "ticker": ticker, "metric": "valuation_methodology", "value": "FCFF discounts unlevered cash flows at WACC and bridges enterprise to common equity. FCFE discounts equity cash flows at cost of equity without deducting net debt again. Historical P/E benchmarks and growth caps are disclosed research policies. Hypothetical recalculation requires the assumptions editor; chat has no calculation or write tool.",
                  "unit": "text", "period": None, "observation_date": None, "retrieved_at": None,
                  "source_url": None, "accession": None, "derivation": None, "quality_warnings": [], "excerpt": None}
        if identity:
            method["identity"] = deepcopy(identity)
        method["id"] = "e_" + hashlib.sha256(json.dumps(method, sort_keys=True).encode()).hexdigest()[:24]
        package["registry"][method["id"]] = method
        package["binding_catalog"] = binding_catalog(package["registry"])
        return package

    def _key(self, owner, package):
        content = [owner, package["ticker"], package["financial_snapshot_id"], package["valuation_snapshot_id"],
                   stable_snapshot_id({"registry": package["registry"], "limitations": package["limitations"],
                                       "adapter_version": package.get("evidence_adapter_version"),
                                       "identity": package.get("identity")}),
                   self.settings.openai_model, PROMPT_VERSION, self.settings.openai_max_output_tokens]
        return hashlib.sha256(json.dumps(content).encode()).hexdigest()

    def _fit_context(self, schema, payload, task):
        """Budget the actual request-scoped schema, not a static allowance.

        The assembler orders whole records by materiality. Trim from its lowest
        priority end, preserving displayed valuation values, count and method.
        No source value, unit, period, warning or provenance field is clipped.
        """
        package = payload.get("evidence", payload)
        registry = package["registry"]
        protected = {"valuation_methodology", "company_profile", "listing_verification", "market_price", "base_fair_value",
                     "base_contributing_model_count", "base_model_name", "forward_eps", "target_pe",
                     "base_model_results", "debt", "wacc", "total_debt"}
        bounded = False
        had_filings = any(item["category"] == "filing_excerpt" for item in registry.values())
        while input_size(schema, payload, task) > self.settings.ai_max_context_tokens:
            removable = next((key for key in reversed(registry) if registry[key]["metric"] not in protected), None)
            if removable is None:
                raise ApiError("ai_context_too_large", "The research context exceeds the configured input budget.", 422)
            registry.pop(removable)
            package["binding_catalog"] = binding_catalog(registry)
            if not bounded:
                package["limitations"].insert(0, "Evidence and binding choices were bounded to the complete request budget; omitted records must not be inferred or cited.")
                bounded = True
            if had_filings and not any(item["category"] == "filing_excerpt" for item in registry.values()):
                package["limitations"].append("No SEC filing passages fit this bounded request; qualitative filing coverage is unavailable for generation.")
                had_filings = False

    def _public(self, owner, package, ids):
        token = secrets.token_urlsafe(32)
        # Only cited public evidence is available using the session-bound capability.
        registry = {key: package["registry"][key] for key in ids}
        identity = deepcopy(package.get("identity"))
        self.snapshots[token] = (time.monotonic() + self.settings.ai_report_cache_ttl, owner, package["ticker"], registry, identity)
        self._prune()
        return {"ticker": package["ticker"], "company_name": package["company_name"],
                "generated_at": datetime.now(UTC).isoformat(), "financial_snapshot_id": package["financial_snapshot_id"],
                "valuation_snapshot_id": package["valuation_snapshot_id"], "snapshot_dates": package["snapshot_dates"],
                "evidence_references": list(registry.values()), "snapshot_token": token,
                **({"identity": identity} if identity else {})}

    async def report(self, ticker, body, owner, instrument_id=None, listing_id=None):
        self.require_available()
        async with self.limits.admission():
            package = await self._context(ticker, body.valuation, instrument_id, listing_id)
            self._fit_context(ReportDraft, package, REPORT_TASK)
            key = self._key(owner, package)
            self._prune()
            if not body.regenerate and key in self.reports:
                cached = deepcopy(self.reports[key][1])
                self.snapshots[cached["snapshot_token"]] = (self.reports[key][0], owner, ticker,
                    {item["id"]: item for item in cached["evidence_references"]}, deepcopy(cached.get("identity")))
                self._prune()
                cached["cache_status"] = "hit"
                return cached
            if key in self.generating:
                raise ApiError("ai_report_in_progress", "This research report is already being generated.", 429)
            self.generating.add(key)
            try:
                self.limits.generation()
                draft = await self.client.generate(ReportDraft, package, REPORT_TASK)
                self._check_private_output(draft)
                sections, ids, withheld = self._validated_sections(draft, package["registry"])
                result = {**self._public(owner, package, ids), "sections": draft.sections.model_dump(),
                          "quality_warnings": package["limitations"] + [QUALITATIVE_WARNING] +
                              (["Partial research report: findings that failed numerical-evidence validation were withheld. Review source details; no unsupported numbers from those findings are displayed."] if withheld else []), "cache_status": "miss"}
                result["sections"] = sections
                self.reports[key] = (time.monotonic() + self.settings.ai_report_cache_ttl, deepcopy(result))
                self._prune()
                return result
            finally:
                self.generating.discard(key)

    async def chat(self, ticker, body, owner, instrument_id=None, listing_id=None):
        self.require_available()
        check_question(body.question, self.private_values)
        for turn in body.history:
            check_question(turn.content, self.private_values)
        async with self.limits.admission():
            package = await self._context(ticker, body.valuation, instrument_id, listing_id)
            # Do not ask the model to recalculate requested hypothetical prices.
            import re
            hypothetical = re.search(r"\b(?:what if|worth if|value if|assuming|recalculate)\b", body.question, re.I)
            if hypothetical:
                method = next(item for item in package["registry"].values() if item["metric"] == "valuation_methodology")
                draft = ChatDraft(answer=[Finding(title="Use the assumptions editor", explanation="Set the hypothetical inputs in the valuation assumptions editor to obtain a deterministic Python calculation. Chat has not changed your assumptions or provider facts.", evidence_ids=[method["id"]], category="interpretation", uncertainty="limited", quantitative_claims=[])])
            else:
                self.limits.generation()
                # Client-provided history is untrusted and never becomes financial evidence.
                payload = {"evidence": package, "question": sanitize(body.question, self.private_values),
                           "history": [sanitize(turn.model_dump(), self.private_values) for turn in body.history[-4:]]}
                while payload["history"] and input_size(ChatDraft, payload, CHAT_TASK) > self.settings.ai_max_context_tokens:
                    payload["history"].pop(0)
                if len(payload["history"]) < len(body.history):
                    package["limitations"].append("Older conversation turns were omitted to preserve the bounded evidence context.")
                self._fit_context(ChatDraft, payload, CHAT_TASK)
                draft = await self.client.generate(ChatDraft, payload, CHAT_TASK)
                self._check_private_output(draft)
            try:
                ids = validate_findings(draft.answer, package["registry"])
                answer = [render_finding(finding, package["registry"]) for finding in draft.answer]
            except ApiError as error:
                error.details = validation_diagnostic(draft.answer, package["registry"], self.private_values)
                raise
            return {**self._public(owner, package, ids), "answer": answer,
                    "limitations": package["limitations"] + [QUALITATIVE_WARNING]}

    def _check_private_output(self, draft):
        data = draft.model_dump()
        if sanitize(data, self.private_values) != data:
            raise ApiError("unsafe_ai_output", "The generated research did not meet privacy checks.", 502)

    def _validated_sections(self, draft, registry):
        sections, references, valid, withheld = {}, set(), 0, 0
        for name in type(draft.sections).model_fields:
            checked = []
            for finding in getattr(draft.sections, name):
                try:
                    ids = validate_findings([finding], registry)
                    valid += 1
                except ApiError as error:
                    if error.code != "unsupported_ai_number":
                        raise
                    # Keep the financial guard unchanged. Discard the entire
                    # unverified finding, rather than editing its numbers or
                    # presenting the original text with a small disclaimer.
                    finding = Finding(title="Finding withheld", explanation="The AI text did not meet numerical-evidence validation and has been withheld. Review the registered source details for this section.",
                                      evidence_ids=finding.evidence_ids, category="unavailable", uncertainty="unavailable", quantitative_claims=[])
                    ids = validate_findings([finding], registry)
                    withheld += 1
                references.update(ids)
                checked.append(render_finding(finding, registry))
            sections[name] = checked
        if not valid:
            raise ApiError("unsupported_ai_number", "No research findings passed numerical-evidence validation. No report was substituted.", 502)
        return sections, sorted(references), withheld

    def evidence(self, ticker, evidence_id, token, owner, instrument_id=None, listing_id=None):
        self._prune()
        record = self.snapshots.get(token)
        if record is None or record[1] != owner or record[2] != ticker or evidence_id not in record[3]:
            raise ApiError("ai_evidence_not_found", "The research evidence is unavailable for this session or has expired.", 404)
        identity = record[4] if len(record) > 4 else None
        if (identity and identity.get("instrument_id") != instrument_id) or (instrument_id is not None and not identity):
            raise ApiError("ai_evidence_not_found", "The research evidence does not belong to the selected instrument.", 404)
        if listing_id is not None and (not identity or identity.get("listing_id") != listing_id):
            raise ApiError("ai_evidence_not_found", "The research evidence does not belong to the selected listing.", 404)
        return deepcopy(record[3][evidence_id])
