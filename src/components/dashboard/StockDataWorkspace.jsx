import { useEffect, useState } from "react";
import { Link } from "react-router";
import { useDataMode } from "@/context/dataMode";
import { loadStock } from "@/services/api";
import { adaptProviderStock } from "@/lib/providerCompatibility";
import { getStockData } from "@/lib/stockRepository";
import { Button } from "@/components/ui/button";
import AnalysisWorkspace from "./AnalysisWorkspace";
import DashboardLayout from "./DashboardLayout";
import DataModeControl from "./DataModeControl";
import { stockLocation, securityFormLabel, listingVerificationSummary } from "@/lib/securityIdentity";

function ProviderWorkspace({ ticker, instrumentId, listingId, retry }) {
  const { setMode } = useDataMode();
  const [state, setState] = useState({ status: "loading" });
  useEffect(() => {
    const controller = new AbortController();
    loadStock(ticker, { signal: controller.signal, instrumentId, listingId })
      .then((data) => {
        if (!controller.signal.aborted)
          setState({ status: "ready", company: adaptProviderStock(data) });
      })
      .catch((error) => {
        if (!controller.signal.aborted) setState({ status: "error", error });
      });
    return () => controller.abort();
  }, [ticker, instrumentId, listingId]);
  if (state.status === "ready")
    return <AnalysisWorkspace key={`${state.company.instrumentId ?? ticker}-${state.company.listingId ?? "legacy"}`} company={state.company} />;
  return (
    <DashboardLayout>
      <DataModeControl />
      <section
        id="overview"
        className="research-section research-data-state"
        aria-live="polite"
        aria-busy={state.status === "loading"}
      >
        {state.status === "loading" ? (
          <>
            <h1>Loading {ticker} financial data…</h1>
            <p>
              Retrieving company information, financial periods, and source
              status from FastAPI.
            </p>
          </>
        ) : (
          <>
            <h1>
              {state.error.status === 404
                ? `Provider data is unavailable for ${ticker}.`
                : `Unable to load ${ticker} provider data.`}
            </h1>
            <p role="alert">{state.error.message}</p>
            {state.error.code === "identity_ambiguous" && <div className="provider-identity-candidates"><p>Select the exchange, share class and listing you intend to research.</p>{(state.error.details?.candidates ?? []).map((candidate) => <Link key={candidate.listing_id ?? candidate.instrument_id} to={stockLocation(candidate)}>{[candidate.ticker, candidate.name, candidate.exchange || "Exchange unverified", securityFormLabel(candidate), candidate.share_class ? `Class ${candidate.share_class}` : "Share class unverified", `CIK ${candidate.cik || "unavailable"}`, candidate.listing_status ? `Listing ${candidate.listing_status.replaceAll("_", " ")}` : "Listing status unverified", listingVerificationSummary(candidate).label, candidate.identity_status && `Identity ${candidate.identity_status.replaceAll("_", " ")}`, candidate.valid_from && `From ${candidate.valid_from}`, candidate.valid_to && `Until ${candidate.valid_to}`, candidate.listing_id && `Listing ID ${candidate.listing_id}`].filter(Boolean).join(" · ")}</Link>)}</div>}
            <p>
              No demonstration figures have been substituted. You can retry or
              intentionally select demonstration mode.
            </p>
            <div className="research-data-actions">
              <Button variant="outline" onClick={retry}>
                Retry provider request
              </Button>
              <Button onClick={() => setMode("demo")}>
                Use demonstration data
              </Button>
            </div>
          </>
        )}
      </section>
    </DashboardLayout>
  );
}

export default function StockDataWorkspace({ ticker, instrumentId, listingId }) {
  const { mode } = useDataMode();
  const [attempt, setAttempt] = useState(0);
  if (mode === "provider")
    return (
      <ProviderWorkspace
        key={`${ticker}-${instrumentId ?? "unresolved"}-${listingId ?? "unresolved"}-${attempt}`}
        ticker={ticker}
        instrumentId={instrumentId}
        listingId={listingId}
        retry={() => setAttempt((value) => value + 1)}
      />
    );
  const company = getStockData(ticker);
  if (company) return <AnalysisWorkspace key={ticker} company={company} />;
  return (
    <DashboardLayout>
      <DataModeControl />
      <section id="overview" className="research-section research-data-state">
        <span className="research-caption">
          DEMONSTRATION DATASET DIRECTORY
        </span>
        <h1>No demo dataset for {ticker}.</h1>
        <p>
          This ticker has no supported demonstration financial data. No
          financial figures have been invented. Try AAPL, MSFT, NVDA, GOOG,
          AMZN, TSLA, ORCL, JPM, KO, or O.
        </p>
        <Button asChild variant="outline">
          <Link to="/dashboard">Open Microsoft Demo</Link>
        </Button>
      </section>
    </DashboardLayout>
  );
}
