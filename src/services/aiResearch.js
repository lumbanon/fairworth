import { ApiError, fetchJson } from "./api.js";

const storageKey = "fairworth.research.session";
let fallbackSession;
const safeSession = /^[a-zA-Z0-9_-]{16,100}$/;

// This opaque identifier scopes temporary evidence access. It is not a login,
// provider credential, or a place to persist research and conversations.
export function researchSession({ storage, randomUUID = () => globalThis.crypto.randomUUID() } = {}) {
  try {
    storage ??= globalThis.sessionStorage;
    const saved = storage?.getItem(storageKey);
    if (saved && safeSession.test(saved)) return saved;
  } catch { /* Private browsing may disable session storage. */ }
  if (!fallbackSession) fallbackSession = randomUUID();
  try { storage?.setItem(storageKey, fallbackSession); } catch { /* Keep an in-memory session. */ }
  return fallbackSession;
}

export function safeEvidenceUrl(value) {
  if (typeof value !== "string" || value.length > 1000 || /\s/.test(value)) return null;
  try {
    const url = new URL(value);
    const paths = {
      "data.sec.gov": ["/api/xbrl/companyfacts/", "/submissions/"],
      "www.sec.gov": ["/Archives/edgar/data/", "/ixviewer/"],
      "home.treasury.gov": ["/resource-center/data-chart-center/interest-rates/", "/treasury-daily-interest-rate-xml-feed"],
      "financialmodelingprep.com": ["/stable/", "/api/"],
    };
    // Check the original path as URL() canonicalizes encoded dot segments.
    const rawPath = value.match(/^https:\/\/[^/?#]+([^?#]*)/i)?.[1] ?? "";
    const decoded = decodeURIComponent(rawPath);
    if (url.protocol !== "https:" || !paths[url.hostname]?.some((prefix) => rawPath.startsWith(prefix)) || url.username || url.password || url.search || url.hash || (url.port && url.port !== "443") || decoded.includes("\\") || decoded.split("/").some((part) => part === "." || part === "..")) return null;
    return url.href;
  } catch { return null; }
}

export function validateResearchResponse(response, ticker, kind = "report") {
  const normalize = (value) => String(value ?? "").toUpperCase().replaceAll(".", "-");
  if (normalize(response?.ticker) !== normalize(ticker))
    throw new ApiError("The research response does not match the selected company.", 0, "incompatible_response");
  const findings = kind === "chat" ? [response.answer] : Object.values(response.sections ?? {});
  const sources = response.evidence_references;
  const invalidFinding = (finding) => typeof finding?.title !== "string" || typeof finding?.explanation !== "string"
    || typeof finding.category !== "string" || typeof finding.uncertainty !== "string"
    || !Array.isArray(finding.evidence_ids) || finding.evidence_ids.some((id) => !sources.some((source) => source.id === id))
    || !Array.isArray(finding.quantitative_claims) || finding.quantitative_claims.some((claim) => typeof claim?.metric !== "string" || typeof claim?.unit !== "string" || !Number.isFinite(claim.value));
  if (!Array.isArray(sources) || sources.some((source) => typeof source?.id !== "string" || typeof source?.title !== "string" || typeof source?.metric !== "string") || !findings.length || findings.some((section) => !Array.isArray(section) || section.some(invalidFinding)))
    throw new ApiError("The research service returned an incomplete response. Please try again.", 0, "invalid_response");
  return response;
}

function request(ticker, path, options = {}) {
  const { session = researchSession(), ...rest } = options;
  return fetchJson(`/stocks/${encodeURIComponent(ticker)}/ai/${path}`, {
    timeoutMs: 100000,
    ...rest,
    headers: { ...rest.headers, "X-Fairworth-Session": session },
  });
}

export function loadResearchStatus(ticker, options) {
  return request(ticker, "status", options);
}

export async function generateResearchReport(ticker, valuation, { regenerate = false, ...options } = {}) {
  const result = await request(ticker, "report", { ...options, method: "POST", body: { ...(valuation ? { valuation } : {}), regenerate } });
  return validateResearchResponse(result, ticker);
}

export async function askResearchQuestion(ticker, question, history, valuation, options) {
  const result = await request(ticker, "chat", { ...options, method: "POST", body: {
    question, history: history.slice(-8).map(({ role, content }) => ({ role, content: content.slice(0, 2000) })), ...(valuation ? { valuation } : {}),
  } });
  return validateResearchResponse(result, ticker, "chat");
}
