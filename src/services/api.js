import { matchingSecurity } from "../lib/securityIdentity.js";

// Provider credentials stay on FastAPI. The browser only calls this API boundary.
const configuredBase =
  import.meta.env?.VITE_API_BASE_URL || "http://127.0.0.1:8000";
export const apiBaseUrl = configuredBase.replace(/\/+$/, "");

export class ApiError extends Error {
  constructor(message, status = 0, code = "network_error", details = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export async function fetchJson(
  path,
  { signal, fetcher = fetch, timeoutMs = 20000, method = "GET", body: requestBody, headers = {}, instrumentId, listingId } = {},
) {
  let response;
  const controller = new AbortController();
  const cancel = () => controller.abort();
  signal?.addEventListener("abort", cancel, { once: true });
  if (signal?.aborted) controller.abort();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  try {
    try {
      const identityParameters = new URLSearchParams();
      if (instrumentId) identityParameters.set("instrument_id", instrumentId);
      if (listingId) identityParameters.set("listing_id", listingId);
      const scopedPath = identityParameters.size ? `${path}${path.includes("?") ? "&" : "?"}${identityParameters}` : path;
      response = await fetcher(`${apiBaseUrl}/api${scopedPath}`, {
        signal: controller.signal,
        method,
        headers: {
          Accept: "application/json",
          ...(requestBody === undefined ? {} : { "Content-Type": "application/json" }),
          ...headers,
        },
        ...(requestBody === undefined ? {} : { body: JSON.stringify(requestBody) }),
      });
    } catch (error) {
      if (timedOut)
        throw new ApiError(
          "The financial data service request timed out. Please try again.",
          0,
          "request_timeout",
        );
      if (error.name === "AbortError") throw error;
      throw new ApiError(
        "The financial data service could not be reached. Check the backend connection and try again.",
      );
    }
    let body;
    try {
      body = await response.json();
    } catch (error) {
      if (timedOut)
        throw new ApiError(
          "The financial data service request timed out. Please try again.",
          0,
          "request_timeout",
        );
      if (error.name === "AbortError") throw error;
      throw new ApiError(
        "The financial data service returned an unreadable response.",
        response.status,
        "invalid_response",
      );
    }
    if (!response.ok) {
      const detail = body?.error ?? body?.detail;
      const message = typeof detail === "string" ? detail : detail?.message;
      throw new ApiError(
        message || "The financial data request failed. Please try again.",
        response.status,
        detail?.code || "request_failed",
        detail?.details ?? null,
      );
    }
    return body;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", cancel);
  }
}

export function loadValuationDefaults(ticker, options) {
  return fetchJson(`/stocks/${encodeURIComponent(ticker)}/valuation/defaults`, options);
}

export function calculateValuation(ticker, request, options) {
  return fetchJson(`/stocks/${encodeURIComponent(ticker)}/valuation/calculate`, {
    ...options,
    method: "POST",
    body: request,
  });
}

export function loadValuationSensitivity(ticker, request, options) {
  return fetchJson(`/stocks/${encodeURIComponent(ticker)}/valuation/sensitivity`, {
    ...options,
    method: "POST",
    body: request,
  });
}

export function searchStocks(query, { limit = 10, offset = 0, ...options } = {}) {
  return fetchJson(`/stocks/search?q=${encodeURIComponent(query)}&limit=${limit}&offset=${offset}`, options);
}

export function loadStockCoverage(ticker, options) {
  return fetchJson(`/stocks/${encodeURIComponent(ticker)}/coverage`, options);
}

export async function loadStock(ticker, options) {
  const path = `/stocks/${encodeURIComponent(ticker)}`;
  const [profile, annual, quarterly, metrics, dataStatus, coverage] =
    await Promise.allSettled([
      fetchJson(path, options),
      fetchJson(`${path}/financials?period=annual`, options),
      fetchJson(`${path}/financials?period=quarterly`, options),
      fetchJson(`${path}/metrics`, options),
      fetchJson(`${path}/data-status`, options),
      loadStockCoverage(ticker, options),
    ]);
  if (profile.status === "rejected") throw profile.reason;
  const requested = { ticker, ...(options?.instrumentId ? { instrument_id: options.instrumentId } : {}), ...(options?.listingId ? { listing_id: options.listingId } : {}) };
  if (!matchingSecurity(profile.value, requested))
    throw new ApiError(
      "The returned financial data does not match the requested company.",
      0,
      "incompatible_response",
    );
  const expected = { ...requested, ...profile.value.company };
  for (const result of [annual, quarterly, metrics, dataStatus, coverage]) {
    if (
      result.status === "fulfilled" &&
      // Older API mocks may not implement the optional coverage endpoint.
      !(result === coverage && !result.value?.stages) &&
      !matchingSecurity(result.value, expected)
    ) {
      throw new ApiError(
        "Optional source data does not match the requested company.",
        0,
        "incompatible_response",
      );
    }
  }
  const optional = [quarterly, metrics, dataStatus];
  return {
    profile: profile.value,
    annual: annual.status === "fulfilled" ? annual.value : null,
    quarterly: quarterly.status === "fulfilled" ? quarterly.value : null,
    metrics: metrics.status === "fulfilled" ? metrics.value : null,
    dataStatus: dataStatus.status === "fulfilled" ? dataStatus.value : null,
    coverage: coverage.status === "fulfilled" && coverage.value?.stages ? coverage.value : null,
    requestWarnings: [...[annual, ...optional].flatMap((result, index) =>
      result.status === "rejected"
        ? [
            {
              field: ["annual", "quarterly", "metrics", "data_status"][index],
              code: result.reason.code || "request_unavailable",
              message: result.reason.message,
            },
          ]
        : [],
    ), ...(coverage.status === "rejected" && coverage.reason.status !== 404 ? [{ field: "coverage", code: coverage.reason.code || "coverage_unavailable", message: `Company coverage diagnostics are unavailable. ${coverage.reason.message}` }] : [])],
  };
}
