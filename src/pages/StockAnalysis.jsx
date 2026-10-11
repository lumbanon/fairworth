import { useParams } from "react-router";
import StockDataWorkspace from "@/components/dashboard/StockDataWorkspace";
import PlaceholderLayout from "@/components/layout/PlaceholderLayout";
import StockSearch from "@/components/landing/StockSearch";
import { isValidTicker, normalizeTicker } from "@/lib/format";

export default function StockAnalysis() {
  const { ticker: routeTicker } = useParams();
  const ticker = normalizeTicker(routeTicker);
  if (!isValidTicker(ticker))
    return (
      <PlaceholderLayout
        title="That ticker format isn’t supported."
        description="Use 1–5 letters with an optional share class, such as AAPL or BRK.B."
      >
        <StockSearch compact dashboard />
      </PlaceholderLayout>
    );
  return <StockDataWorkspace key={ticker} ticker={ticker} />;
}
