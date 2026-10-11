export default function ResearchInsights({ company }) {
  const provider = company.dataMode === "provider";
  return (
    <section
      id="insights"
      className="research-section"
      aria-labelledby="insights-heading"
    >
      <div className="research-section-heading">
        <div>
          <h2 id="insights-heading">Research insights</h2>
          <p>
            Research insights preview — AI analysis will be available in a later
            phase.
          </p>
        </div>
        <span className="research-caption">
          {provider
            ? "Research checklist · no automated company report"
            : "Static demonstration commentary"}
        </span>
      </div>
      <div className="research-insights">
        <article>
          <h3>Business context</h3>
          <p>
            {company.description ||
              "Review the original SEC filings and available company profile for business context."}
          </p>
        </article>
        <article>
          <h3>Questions to investigate</h3>
          <p>
            {company.isBank
              ? "How durable are returns on equity, credit quality, and capital distributions? The residual-income framework assumes clean-surplus accounting."
              : company.isREIT
                ? "How sustainable is AFFO after recurring property costs? This framework does not model property NAV, lease expirations, or acquisition funding."
                : "How durable are margins and cash conversion? Long-term growth and discount rates can dominate a discounted cash-flow estimate."}
          </p>
        </article>
        <article>
          <h3>Model disagreement</h3>
          <p>
            Different approaches emphasize different economic drivers. Inspect
            the spread, input quality, and applicability before choosing
            weights. Several models share correlated assumptions.
          </p>
        </article>
        <article>
          <h3>Limitations and risks</h3>
          <p>
            {provider ? (
              "Reported source data may be partial, stale, or incompatible with a valuation method. Check filing dates, share-count bases, missing fields, and source notices before entering assumptions. No AI-generated analysis is provided."
            ) : (
              <>
                These fictional statements omit detailed working capital,
                capital structure changes, dilution schedules, and regulatory
                constraints. This commentary is fixed; it does not describe the
                current edited valuation or real market conditions.
              </>
            )}
          </p>
        </article>
      </div>
    </section>
  );
}
