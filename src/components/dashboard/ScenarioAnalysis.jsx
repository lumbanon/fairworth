import { dollars, percent, direction } from "@/lib/financialFormatting";
import { scenarioNames } from "@/valuation/scenarios";

export default function ScenarioAnalysis({ valuation }) {
  return (
    <section
      id="scenarios"
      className="research-section"
      aria-labelledby="scenarios-heading"
    >
      <div className="research-section-heading">
        <div>
          <h2 id="scenarios-heading">Scenario analysis</h2>
          <p>
            Three independently editable perspectives, using the same reference
            price and model weights.
          </p>
        </div>
      </div>
      <div className="research-scenarios">
        {scenarioNames.map((name) => {
          const result = valuation.scenarios[name].summary;
          return (
            <button
              key={name}
              className={`research-scenario ${valuation.activeScenario === name ? "selected" : ""}`}
              aria-pressed={valuation.activeScenario === name}
              aria-label={`Select ${name} scenario`}
              onClick={() => valuation.setActiveScenario(name)}
            >
              <span>{name[0].toUpperCase() + name.slice(1)} Case</span>
              <strong>{dollars(result.fairValue)}</strong>
              <span className={direction(result.upside)}>
                {percent(result.upside, true)} potential return
              </span>
              <small>
                {result.count} contributing models
                {valuation.activeScenario === name ? " · Active scenario" : ""}
              </small>
            </button>
          );
        })}
      </div>
      <p className="research-caption">
        The bear/bull range represents assumption choices, not a statistical
        confidence interval. Edits can change the ordering of scenarios.
      </p>
    </section>
  );
}
