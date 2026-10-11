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

function ProviderWorkspace({ ticker, retry }) {
  const { setMode } = useDataMode();
  const [state, setState] = useState({ status: "loading" });
  useEffect(() => {
    const controller = new AbortController();
    loadStock(ticker, { signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted)
          setState({ status: "ready", company: adaptProviderStock(data) });
      })
      .catch((error) => {
        if (!controller.signal.aborted) setState({ status: "error", error });
      });
    return () => controller.abort();
  }, [ticker]);
  if (state.status === "ready")
    return <AnalysisWorkspace key={ticker} company={state.company} />;
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

export default function StockDataWorkspace({ ticker }) {
  const { mode } = useDataMode();
  const [attempt, setAttempt] = useState(0);
  if (mode === "provider")
    return (
      <ProviderWorkspace
        key={`${ticker}-${attempt}`}
        ticker={ticker}
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
