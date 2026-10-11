import { dollars, percent, direction } from "@/lib/financialFormatting";

export default function ValuationSummary({ company, valuation }) {
  const { summary, scenarios, activeScenario } = valuation;
  const enabledCount = valuation.results.filter(
    (result) => result.applicable && valuation.enabled[result.id],
  ).length;
  const range = [
    scenarios.bear.summary.fairValue,
    scenarios.bull.summary.fairValue,
  ];
  const finiteRange = range.every(Number.isFinite);
  return (
    <section className="research-summary" aria-labelledby="summary-title">
      <div className="research-section-heading">
        <h2 id="summary-title">Valuation overview</h2>
        <span className="research-caption">
          {activeScenario[0].toUpperCase() + activeScenario.slice(1)} scenario ·
          calculated locally
        </span>
      </div>
      <div className="research-metrics">
        <div>
          <span>Market price</span>
          <strong>
            {dollars(
              company.price,
              company.dataMode === "provider"
                ? (company.market?.currency ?? null)
                : "USD",
            )}
          </strong>
          <small>
            {company.dataMode === "provider"
              ? company.price == null
                ? "Market provider price unavailable"
                : "Provider price · timestamp above"
              : "Fictional reference price"}
          </small>
        </div>
        <div>
          <span>Weighted fair value</span>
          <strong data-testid="weighted-fair-value" className="research-accent">
            {dollars(summary.fairValue)}
          </strong>
          <small>
            {enabledCount} enabled · {summary.count} contributing
          </small>
        </div>
        <div>
          <span>Potential upside / downside</span>
          <strong
            data-testid="summary-upside"
            className={direction(summary.upside)}
          >
            {percent(summary.upside, true)}
          </strong>
          <small>(Fair value / price − 1) × 100</small>
        </div>
        <div>
          <span>Margin of safety</span>
          <strong className={direction(summary.marginOfSafety)}>
            {percent(summary.marginOfSafety, true)}
          </strong>
          <small>(Fair value − price) / fair value × 100</small>
        </div>
      </div>
      <div className="research-summary-bottom">
        <span>
          Bear / bull fair values{" "}
          <strong>
            {finiteRange
              ? `${dollars(range[0])} / ${dollars(range[1])}`
              : "Unavailable"}
          </strong>
        </span>
        <span>
          Model estimates are uncertain; a weighted average does not guarantee
          accuracy.
        </span>
      </div>
      {summary.warnings.length > 0 && (
        <div role="alert" className="research-warning">
          {summary.warnings.map((warning) => (
            <p key={warning}>{warning}</p>
          ))}
        </div>
      )}
    </section>
  );
}
