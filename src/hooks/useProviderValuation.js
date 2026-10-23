import { useEffect, useMemo, useState } from "react";
import { calculateValuation, loadValuationDefaults } from "@/services/api";
import { adaptProviderValuation, emptyProviderValuation, providerInputErrors, providerModelIds, providerScenarioNames } from "@/lib/providerValuation";

const sensitivityChoices = {
  pe: { model_id: "pe", x_parameter: "target_pe", y_parameter: "forward_eps" },
  fcff: { model_id: "fcff", x_parameter: "terminal_growth", y_parameter: "wacc" },
  fcffOperating: { model_id: "fcff", x_parameter: "revenue_growth", y_parameter: "operating_margin" },
  fcfe: { model_id: "fcfe", x_parameter: "terminal_growth", y_parameter: "cost_of_equity" },
  evEbitda: { model_id: "evEbitda", x_parameter: "target_ev_ebitda", y_parameter: "forecast_ebitda" },
  evRevenue: { model_id: "evRevenue", x_parameter: "target_ev_revenue", y_parameter: "forecast_revenue" },
};

export default function useProviderValuation(company) {
  const [state, setState] = useState({ status: "loading", response: null, defaults: null, error: null });
  const [activeScenario, setActiveScenario] = useState("base");
  const [overrides, setOverrides] = useState({ bear: {}, base: {}, bull: {} });
  const [configuredWeights, setConfiguredWeights] = useState(null);
  const [enabledOverrides, setEnabledOverrides] = useState(null);
  const [manualPrice, setManualPrice] = useState(null);
  const [sensitivitySelection, setSensitivitySelection] = useState("pe");
  const [defaultsAttempt, setDefaultsAttempt] = useState(0);
  const [calculationAttempt, setCalculationAttempt] = useState(0);
  const [datedIntrinsic, setDatedIntrinsic] = useState(false);
  const [evidenceAsOf, setEvidenceAsOf] = useState("");
  const data = useMemo(() => state.response ? adaptProviderValuation(state.response) : emptyProviderValuation(), [state.response]);
  const initialDefaults = state.defaults ?? {};
  const weights = configuredWeights ?? data.configuredWeights;
  const enabled = enabledOverrides ?? Object.fromEntries(providerModelIds.map((id) => [id, data.enabledModels.includes(id)]));
  const datedKeys = ["dividend_growth", "cost_of_equity", "stable_dividend_confirmed"];
  const effectiveOverrides = datedIntrinsic
    ? Object.fromEntries(providerScenarioNames.map((name) => [name, Object.fromEntries(Object.entries(overrides[name]).filter(([key]) => datedKeys.includes(key)))]))
    : overrides;
  const validationErrors = providerInputErrors(effectiveOverrides.base, { bear: effectiveOverrides.bear, bull: effectiveOverrides.bull }, datedIntrinsic ? null : configuredWeights, datedIntrinsic ? null : manualPrice);
  if (datedIntrinsic) {
    if (!/T.*(?:Z|[+-]\d{2}:\d{2})$/.test(evidenceAsOf) || !Number.isFinite(Date.parse(evidenceAsOf))) validationErrors.push("Enter a dated evidence timestamp with a timezone, within the original listing and issuer proof interval.");
    if (!Number.isFinite(effectiveOverrides.base.dividend_growth) || !Number.isFinite(effectiveOverrides.base.cost_of_equity) || effectiveOverrides.base.stable_dividend_confirmed !== true) validationErrors.push("Dated intrinsic analysis requires explicit dividend growth, required return and a sustainable-dividend assumption.");
  }
  const request = {
    assumptions: effectiveOverrides.base,
    scenario_overrides: { bear: effectiveOverrides.bear, bull: effectiveOverrides.bull },
    ...(datedIntrinsic ? { context: "dated_intrinsic", evidence_as_of: evidenceAsOf, enabled_models: ["dividend"] } : {
      ...(configuredWeights ? { weights: configuredWeights } : {}),
      ...(enabledOverrides ? { enabled_models: Object.keys(enabledOverrides).filter((id) => enabledOverrides[id]) } : {}),
    }),
    manual_market_price: datedIntrinsic || manualPrice === null ? null : { value: manualPrice, currency: company.currency },
    sensitivity: datedIntrinsic ? null : sensitivityChoices[sensitivitySelection],
  };
  const requestKey = JSON.stringify(request);
  const ready = state.defaults !== null || datedIntrinsic;
  const validInputs = validationErrors.length === 0;

  useEffect(() => {
    if (datedIntrinsic) return;
    const controller = new AbortController();
    loadValuationDefaults(company.ticker, { signal: controller.signal, instrumentId: company.instrumentId, listingId: company.listingId })
      .then((response) => {
        adaptProviderValuation(response, company.identity ?? company.ticker);
        if (!controller.signal.aborted)
          setState({ status: "ready", response, defaults: response.defaults, error: null });
      })
      .catch((error) => {
        if (!controller.signal.aborted) setState({ status: "error", response: null, defaults: null, error });
      });
    return () => controller.abort();
  }, [company.ticker, company.identity, company.instrumentId, company.listingId, defaultsAttempt, datedIntrinsic]);

  useEffect(() => {
    if (!ready || !validInputs) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      setState((previous) => ({ ...previous, status: "calculating", error: null }));
      calculateValuation(company.ticker, JSON.parse(requestKey), { signal: controller.signal, instrumentId: company.instrumentId, listingId: company.listingId })
        .then((response) => {
          adaptProviderValuation(response, company.identity ?? company.ticker);
          if (!controller.signal.aborted)
            setState((previous) => ({ ...previous, status: "ready", response, error: null }));
        })
        .catch((error) => {
          if (!controller.signal.aborted)
            setState((previous) => ({ ...previous, status: "error", error }));
        });
    }, 300);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [company.ticker, company.identity, company.instrumentId, company.listingId, requestKey, ready, validInputs, calculationAttempt]);

  const unavailable = state.status === "error" || !validInputs;
  const scenarios = unavailable ? Object.fromEntries(providerScenarioNames.map((name) => [name, {
    ...data.scenarios[name],
    results: data.scenarios[name].results.map((result) => ({ ...result, fairValue: null, upside: null, status: "insufficient-data", classification: "unavailable" })),
    summary: { ...emptyProviderValuation().scenarios[name].summary, classification: "unavailable" },
    confidence: null, diagnostics: null, dataCompleteness: null,
    publication: null,
    independence: null,
    intrinsic: null,
    marketComparison: null,
  }])) : data.scenarios;
  return {
    ...data,
    providerMode: true,
    valuationRequest: JSON.parse(requestKey),
    validForResearch: validInputs && state.status === "ready",
    status: state.status,
    error: state.error,
    validationErrors,
    activeScenario,
    setActiveScenario,
    defaults: initialDefaults,
    assumptions: Object.fromEntries(providerScenarioNames.map((name) => [name, {
      ...(data.scenarios[name].values ?? initialDefaults[name]?.values ?? {}),
      ...overrides[name],
    }])),
    assumptionMetadata: data.scenarios[activeScenario].metadata,
    overriddenKeys: Object.keys({ ...overrides.base, ...overrides[activeScenario] }),
    resettableKeys: Object.keys(overrides[activeScenario]),
    enabled,
    setEnabled: (update) => setEnabledOverrides((previous) => typeof update === "function" ? update(previous ?? enabled) : update),
    weights,
    setWeights: (update) => setConfiguredWeights((previous) => typeof update === "function" ? update(previous ?? weights) : update),
    manualPrice,
    setManualPrice,
    ...(datedIntrinsic ? { comparisonPrice: null, market: { ...data.market, price: null, source_type: "unavailable", label: "No market comparison in dated intrinsic mode" } } : {}),
    datedIntrinsic,
    setDatedIntrinsic,
    evidenceAsOf,
    setEvidenceAsOf,
    datedAssumptions: overrides.base,
    editDatedAssumption: (key, value) => setOverrides((previous) => ({ ...previous, base: { ...previous.base, [key]: value } })),
    sensitivitySelection,
    setSensitivitySelection,
    editAssumption: (key, value) => setOverrides((previous) => ({ ...previous, [activeScenario]: { ...previous[activeScenario], [key]: value } })),
    resetAssumption: (key) => setOverrides((previous) => {
      const next = { ...previous[activeScenario] };
      delete next[key];
      return { ...previous, [activeScenario]: next };
    }),
    resetAssumptions: () => setOverrides((previous) => ({ ...previous, [activeScenario]: {} })),
    resetWeights: () => { setConfiguredWeights(null); setEnabledOverrides(null); },
    retry: () => ready ? setCalculationAttempt((previous) => previous + 1) : setDefaultsAttempt((previous) => previous + 1),
    scenarios,
    sensitivity: unavailable ? null : data.sensitivity,
    reverseDCF: unavailable ? null : data.reverseDCF,
    ...scenarios[activeScenario],
  };
}
