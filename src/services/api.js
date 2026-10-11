// Provider credentials stay on FastAPI. The browser only calls this API boundary.
const configuredBase =
  import.meta.env?.VITE_API_BASE_URL || "http://127.0.0.1:8000";
export const apiBaseUrl = configuredBase.replace(/\/+$/, "");

export class ApiError extends Error {
  constructor(message, status = 0, code = "network_error") {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export async function fetchJson(
  path,
  { signal, fetcher = fetch, timeoutMs = 20000 } = {},
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
      response = await fetcher(`${apiBaseUrl}/api${path}`, {
        signal: controller.signal,
        headers: { Accept: "application/json" },
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
      );
    }
    return body;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", cancel);
  }
}

export function searchStocks(query, options) {
  return fetchJson(`/stocks/search?q=${encodeURIComponent(query)}`, options);
}

export async function loadStock(ticker, options) {
  const path = `/stocks/${encodeURIComponent(ticker)}`;
  const [profile, annual, quarterly, metrics, dataStatus] =
    await Promise.allSettled([
      fetchJson(path, options),
      fetchJson(`${path}/financials?period=annual`, options),
      fetchJson(`${path}/financials?period=quarterly`, options),
      fetchJson(`${path}/metrics`, options),
      fetchJson(`${path}/data-status`, options),
    ]);
  if (profile.status === "rejected") throw profile.reason;
  if (annual.status === "rejected") throw annual.reason;
  const identity = (value) =>
    String(value ?? "")
      .toUpperCase()
      .replace(".", "-");
  if (
    identity(profile.value?.company?.ticker) !== identity(ticker) ||
    identity(annual.value?.ticker) !== identity(ticker)
  )
    throw new ApiError(
      "The returned financial data does not match the requested company.",
      0,
      "incompatible_response",
    );
  for (const result of [quarterly, metrics, dataStatus]) {
    if (
      result.status === "fulfilled" &&
      identity(result.value?.ticker) !== identity(ticker)
    ) {
      result.status = "rejected";
      result.reason = new ApiError(
        "Optional source data does not match the requested company.",
        0,
        "incompatible_response",
      );
    }
  }
  const optional = [quarterly, metrics, dataStatus];
  return {
    profile: profile.value,
    annual: annual.value,
    quarterly: quarterly.status === "fulfilled" ? quarterly.value : null,
    metrics: metrics.status === "fulfilled" ? metrics.value : null,
    dataStatus: dataStatus.status === "fulfilled" ? dataStatus.value : null,
    requestWarnings: optional.flatMap((result, index) =>
      result.status === "rejected"
        ? [
            {
              field: ["quarterly", "metrics", "data_status"][index],
              code: "request_unavailable",
              message: result.reason.message,
            },
          ]
        : [],
    ),
  };
}
