import { useParams, useSearchParams } from "react-router";
import StockDataWorkspace from "@/components/dashboard/StockDataWorkspace";
import PlaceholderLayout from "@/components/layout/PlaceholderLayout";
import StockSearch from "@/components/landing/StockSearch";
import { isValidTicker, normalizeTicker } from "@/lib/format";

export default function StockAnalysis() {
  const { ticker: routeTicker } = useParams();
  const [parameters] = useSearchParams();
  const instrumentId = parameters.get("instrument_id") || null;
  const listingId = parameters.get("listing_id") || null;
  const ticker = normalizeTicker(routeTicker);
  if (!isValidTicker(ticker))
    return (
      <PlaceholderLayout
        title="That ticker format isn’t supported."
        description="Use a valid US listing symbol, such as AAPL or BRK.B, or choose a company from search."
      >
        <StockSearch compact dashboard />
      </PlaceholderLayout>
    );
  return <StockDataWorkspace key={`${ticker}-${instrumentId ?? "unresolved"}-${listingId ?? "unresolved"}`} ticker={ticker} instrumentId={instrumentId} listingId={listingId} />;
}
