import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { modelDefinitions } from "@/data/modelDefinitions";
import { assumptionDefinitions } from "@/data/assumptionDefinitions";
import { number } from "@/lib/financialFormatting";

export default function AssumptionEditor({
  selectedModel,
  setSelectedModel,
  valuation,
  providerMode = false,
}) {
  const model = modelDefinitions.find((item) => item.id === selectedModel);
  const assumptions = valuation.assumptions[valuation.activeScenario];
  const defaults = valuation.defaults[valuation.activeScenario];
  const result = valuation.results.find((item) => item.id === selectedModel);
  const applicableModels = valuation.results.filter((item) => item.applicable);
  if (!applicableModels.length)
    return (
      <section
        id="assumptions"
        className="research-section assumptions-editor"
        aria-labelledby="assumptions-title"
      >
        <h2 id="assumptions-title">Assumptions</h2>
        <p className="research-body-copy">
          No valuation method has compatible required financial inputs. Review
          the model details and data quality notices. Financial facts are not
          invented to enable a model.
        </p>
      </section>
    );
  return (
    <section
      id="assumptions"
      className="research-section assumptions-editor"
      aria-labelledby="assumptions-title"
    >
      <div className="research-section-heading">
        <div>
          <h2 id="assumptions-title">Assumptions</h2>
          <p>
            Edit the {valuation.activeScenario} case. Each scenario keeps its
            own values.
            {providerMode &&
              " Forward inputs are user assumptions, separate from reported financial facts."}
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={valuation.resetAssumptions}
        >
          Reset to Default
        </Button>
      </div>
      <div className="assumption-model-select">
        <label htmlFor="assumption-model">Valuation method</label>
        <select
          id="assumption-model"
          value={selectedModel}
          onChange={(event) => setSelectedModel(event.target.value)}
        >
          {applicableModels.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
      </div>
      <p className="research-body-copy">{model.description}</p>
      <div className="assumption-grid">
        {model.assumptions.map((key) => {
          const definition = assumptionDefinitions[key];
          const multiplier = definition.unit === "%" ? 100 : 1;
          const current = assumptions[key];
          const display =
            typeof current === "number" && Number.isFinite(current)
              ? Number((current * multiplier).toFixed(6))
              : "";
          const baseDisplay = Number.isFinite(defaults[key])
            ? defaults[key] * multiplier
            : null;
          const invalid =
            display === "" ||
            display < definition.min ||
            display > definition.max ||
            (key === "forecastYears" && !Number.isInteger(display));
          function onChange(event) {
            const next = event.target.value;
            valuation.editAssumption(
              key,
              next === "" ? "" : Number(next) / multiplier,
            );
          }
          return (
            <div key={key} className="assumption-field">
              <label htmlFor={`assumption-${key}`}>
                {definition.label}
                <span id={`assumption-unit-${key}`} aria-hidden="true">
                  {definition.unit}
                </span>
              </label>
              <Input
                id={`assumption-${key}`}
                type="number"
                step={definition.step}
                value={display}
                onChange={onChange}
                aria-invalid={invalid}
                aria-describedby={`assumption-unit-${key} assumption-help-${key}`}
                className="research-number-input"
              />
              <div className="assumption-default">
                {providerMode
                  ? key === "shares"
                    ? `Reported diluted weighted shares: ${number(baseDisplay)} ${definition.unit}`
                    : "User assumption · not supplied by the provider"
                  : `Default: ${number(baseDisplay)} ${definition.unit}`}
              </div>
              {key !== "shares" && (
                <input
                  type="range"
                  min={definition.min}
                  max={definition.max}
                  step={definition.step}
                  value={
                    display === ""
                      ? definition.min
                      : Math.max(
                          definition.min,
                          Math.min(definition.max, display),
                        )
                  }
                  aria-label={`${definition.label} slider`}
                  onChange={onChange}
                />
              )}
              <p id={`assumption-help-${key}`}>
                {definition.explanation}
                {invalid && (
                  <span className="negative">
                    {" "}
                    Enter a valid value from {definition.min} to{" "}
                    {definition.max} {definition.unit}.
                  </span>
                )}
              </p>
            </div>
          );
        })}
      </div>
      {result.status !== "valid" && (
        <div role="alert" className="research-warning">
          {result.warnings.map((warning) => (
            <p key={warning}>{warning}</p>
          ))}
        </div>
      )}
    </section>
  );
}
