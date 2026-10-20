import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { number } from "@/lib/financialFormatting";
import { providerEditableAssumptions } from "@/lib/providerValuation";
import ProviderAssumptionSource from "./ProviderAssumptionSource";

const fields = {
  fcff: ["revenue_growth", "operating_margin", "cash_flow_growth", "wacc", "terminal_growth", "forecast_years"],
  fcfe: ["cash_flow_growth", "cost_of_equity", "terminal_growth", "forecast_years", "net_borrowing", "change_nwc"],
  pe: ["earnings_growth", "forward_eps", "target_pe"],
  evEbitda: ["revenue_growth", "ebitda_margin", "forecast_ebitda", "target_ev_ebitda"],
  evRevenue: ["revenue_growth", "forecast_revenue", "target_ev_revenue"],
  peg: ["earnings_growth", "forward_eps", "target_peg"],
  graham: [],
  dividend: ["dividend_growth", "cost_of_equity", "stable_dividend_confirmed"],
  residual: ["return_on_equity", "payout_ratio", "cost_of_equity", "terminal_growth", "forecast_years", "clean_surplus_confirmed"],
  pb: ["target_pb", "book_value_meaningful"],
  affo: ["target_p_affo"],
};
const definitions = {
  revenue_growth: ["Revenue growth", "fraction"], earnings_growth: ["EPS growth", "fraction"],
  cash_flow_growth: ["Cash flow growth", "fraction"], operating_margin: ["Operating margin", "fraction"],
  ebitda_margin: ["Forecast EBITDA margin", "fraction"], terminal_growth: ["Terminal growth", "fraction"],
  wacc: ["WACC", "fraction"], cost_of_equity: ["Cost of equity", "fraction"], tax_rate: ["Tax rate", "fraction"],
  target_pe: ["Target Forward P/E", "multiple"], target_ev_ebitda: ["Target EV/EBITDA", "multiple"],
  target_ev_revenue: ["Target EV/Revenue", "multiple"], target_peg: ["Target PEG", "multiple"],
  target_pb: ["Target P/B", "multiple"], target_p_affo: ["Target P/AFFO", "multiple"],
  forecast_years: ["Forecast period", "years"], dividend_growth: ["Dividend growth", "fraction"],
  return_on_equity: ["Forecast return on equity", "fraction"], payout_ratio: ["Dividend payout ratio", "fraction"],
  terminal_roe: ["Terminal return on equity", "fraction"], capex_ratio: ["Capital expenditure / revenue", "fraction"],
  da_ratio: ["D&A / revenue", "fraction"], nwc_ratio: ["Working capital / revenue", "fraction"],
  forward_eps: ["Forward EPS", "currency/share"], forecast_revenue: ["Forecast revenue", "currency"],
  forecast_ebitda: ["Forecast EBITDA", "currency"], fcff: ["Starting FCFF", "currency"], fcfe: ["Starting FCFE", "currency"],
  net_borrowing: ["Net borrowing", "currency"], change_nwc: ["Change in working capital", "currency"],
  preferred_equity: ["Preferred equity claim", "currency"], minority_interest: ["Minority interest claim", "currency"],
  other_nonoperating_assets: ["Other nonoperating assets", "currency"], shares: ["Valuation shares", "shares"],
  projected_fcff: ["Annual projected FCFF", "currency"], projected_fcfe: ["Annual projected FCFE", "currency"],
  projected_dividends: ["Annual projected dividends per share", "currency/share"],
  projected_revenue: ["Annual projected revenue", "currency"],
  affo: ["Reliable AFFO", "currency"], forecast_affo: ["Forecast AFFO", "currency"], affo_basis_confirmed: ["AFFO financial basis verified", "boolean"],
  is_bank: ["Financial institution classification", "boolean"], is_reit: ["REIT classification", "boolean"],
  growth_fade_to_terminal: ["Forecast growth fades toward terminal growth", "boolean"],
  net_margin: ["Forecast net margin", "fraction"], lookback_years: ["Historical lookback", "fiscal years"],
  book_value_meaningful: ["Book value is economically meaningful", "boolean"],
  common_equity_basis_confirmed: ["Book equity belongs to common shareholders", "boolean"],
  book_equity: ["Common book equity", "currency"],
  clean_surplus_confirmed: ["Clean-surplus framework confirmed", "boolean"],
  stable_dividend_confirmed: ["Sustainable dividend policy confirmed", "boolean"],
  share_basis_confirmed: ["Ticker share basis verified", "boolean"],
};
const advancedFields = ["shares", "share_basis_confirmed", "fcff", "fcfe", "projected_fcff", "projected_fcfe", "projected_revenue", "net_borrowing", "change_nwc", "tax_rate", "capex_ratio", "da_ratio", "nwc_ratio", "preferred_equity", "minority_interest", "other_nonoperating_assets", "terminal_roe", "book_value_meaningful", "common_equity_basis_confirmed", "clean_surplus_confirmed", "stable_dividend_confirmed"];

function AssumptionField({ field, valuation, currency }) {
  const metadata = valuation.assumptionMetadata[field] ?? valuation.defaults[valuation.activeScenario]?.metadata?.[field] ?? {};
  const overridden = valuation.overriddenKeys.includes(field);
  const resettable = (valuation.resettableKeys ?? valuation.overriddenKeys).includes(field);
  const current = metadata.computed_only && !overridden && Number.isFinite(metadata.value)
    ? metadata.value : valuation.assumptions[valuation.activeScenario][field];
  const [label, fallbackUnit] = definitions[field] ?? [field.replaceAll("_", " "), metadata.unit || "number"];
  const unit = metadata.unit || fallbackUnit;
  const percentage = unit === "fraction";
  const boolean = unit === "boolean" || fallbackUnit === "boolean";
  const annualSeries = ["projected_fcff", "projected_fcfe", "projected_dividends", "projected_revenue"].includes(field);
  const multiplier = percentage ? 100 : 1;
  const displayUnit = percentage ? "%" : unit === "multiple" ? "×" : fallbackUnit === "currency" ? currency : fallbackUnit === "currency/share" ? `${currency}/share` : unit;
  const display = Number.isFinite(current) ? Number((current * multiplier).toFixed(6)) : "";
  const suggested = valuation.defaults[valuation.activeScenario]?.values?.[field] ?? valuation.defaults[valuation.activeScenario]?.metadata?.[field]?.value;
  return (
    <div className="assumption-field">
      <label htmlFor={`provider-assumption-${field}`}>{label}<span aria-hidden="true">{boolean ? "" : displayUnit}</span></label>
      {annualSeries ? (
        <Input id={`provider-assumption-${field}`} type="text" value={Array.isArray(current) ? current.join(", ") : typeof current === "string" ? current : ""}
          placeholder="Year 1, year 2, …" aria-describedby={`provider-assumption-help-${field}`} className="research-number-input" disabled={metadata.editable === false}
          onChange={(event) => {
            const raw = event.target.value;
            const values = raw.split(",").map((part) => part.trim());
            const parsed = values.map(Number);
            valuation.editAssumption(field, values.every((part) => part !== "") && parsed.every(Number.isFinite) ? parsed : raw);
          }} />
      ) : boolean ? (
        <select id={`provider-assumption-${field}`} value={typeof current === "boolean" ? String(current) : ""} disabled={metadata.editable === false}
          onChange={(event) => event.target.value === "" ? valuation.resetAssumption(field) : valuation.editAssumption(field, event.target.value === "true")}
          aria-describedby={`provider-assumption-help-${field}`}>
          <option value="">Not confirmed</option><option value="true">Yes · user confirmation</option><option value="false">No · user assertion</option>
        </select>
      ) : (
        <Input id={`provider-assumption-${field}`} type="number" step={unit === "years" ? "1" : "any"}
          value={display} placeholder={metadata.computed_only && Number.isFinite(metadata.value) ? `Computed: ${number(metadata.value * multiplier)}` : undefined}
          onChange={(event) => valuation.editAssumption(field, event.target.value === "" ? "" : Number(event.target.value) / multiplier)}
          disabled={metadata.editable === false} className="research-number-input"
          aria-invalid={current === ""} aria-describedby={`provider-assumption-help-${field}`} />
      )}
      <div className="assumption-default">Suggested: {typeof suggested === "boolean" ? String(suggested) : Array.isArray(suggested) ? `${suggested.map(number).join(", ")} ${displayUnit}` : Number.isFinite(suggested) ? `${number(suggested * multiplier)} ${displayUnit}` : "Requires a supported input"}</div>
      {metadata.computed_only && Number.isFinite(metadata.value) && <p className="research-caption">Computed from current assumptions: {number(metadata.value * multiplier)} {displayUnit}. Enter a value only to override that forecast.</p>}
      <ProviderAssumptionSource metadata={metadata} overridden={overridden} id={`provider-assumption-help-${field}`} />
      {annualSeries && <p className="research-caption">{field === "projected_revenue" ? "Comma-separated positive annual revenue amounts in absolute reporting-currency units, one for each forecast year. Cash-flow calculations still require complete reinvestment, financing and financial-basis inputs." : field === "projected_dividends" ? "Comma-separated annual dividends per share, one for each explicit forecast year." : "Comma-separated annual cash flows, one for each explicit forecast year. Negative early cash flows are permitted; a sustainable terminal basis is still required."}</p>}
      {overridden && !resettable && <p className="research-caption">Inherited from the primary base assumption. Select the Base scenario to reset that input, or enter an independent value for this case.</p>}
      {resettable && <button className="research-text-button" onClick={() => valuation.resetAssumption(field)}>Reset {label}</button>}
    </div>
  );
}

export default function ProviderAssumptionEditor({ selectedModel, setSelectedModel, valuation, currency }) {
  const selected = valuation.results.find((model) => model.id === selectedModel);
  const primary = fields[selectedModel] ?? [];
  const advanced = [...new Set([...advancedFields, ...Object.keys(valuation.assumptionMetadata)])].filter((field) => !primary.includes(field) && providerEditableAssumptions.has(field));
  return (
    <section id="assumptions" className="research-section assumptions-editor" aria-labelledby="assumptions-title">
      <div className="research-section-heading"><div>
        <h2 id="assumptions-title">Assumptions</h2>
        <p>{valuation.activeScenario === "base" ? "Edit primary base assumptions. Python adjusts unedited bear and bull cases from this basis; explicit scenario overrides are preserved." : `Edit the ${valuation.activeScenario} case independently. Primary base assumptions and the other scenario overrides are preserved.`} Reported financial statements remain unchanged.</p>
      </div><Button variant="outline" size="sm" onClick={valuation.resetAssumptions}>Reset to Default</Button></div>
      <div className="assumption-model-select"><label htmlFor="assumption-model">Valuation method</label>
        <select id="assumption-model" value={selectedModel} onChange={(event) => setSelectedModel(event.target.value)}>
          {valuation.results.map((model) => <option key={model.id} value={model.id}>{model.name}</option>)}
        </select>
      </div>
      {selected?.warnings?.map((warning, index) => <p className="research-caption" key={index}>{warning}</p>)}
      {selected?.eligibility?.missing_inputs?.length > 0 && <p className="research-caption"><strong>Required next inputs: </strong>{selected.eligibility.missing_inputs.map((field) => definitions[field]?.[0] ?? field.replaceAll("_", " ")).join(", ")}. Enter a supported estimate below or review the financial basis before confirming its scope.</p>}
      <div className="assumption-grid">{primary.map((field) => <AssumptionField key={field} field={field} valuation={valuation} currency={currency} />)}</div>
      <details className="provider-advanced-assumptions"><summary>Advanced assumptions and missing-input confirmations</summary>
        <p className="research-caption">Financial amounts use absolute {currency} and shares use actual counts. A zero claim or financing input is an explicit user assertion. Confirm scope only after reviewing source disclosures.</p>
        <div className="assumption-grid">{advanced.map((field) => <AssumptionField key={field} field={field} valuation={valuation} currency={currency} />)}</div>
      </details>
      <details className="provider-advanced-assumptions provider-assumption-inventory"><summary>All assumption sources and methods</summary>
        <p className="research-caption">Facts, estimates, policies and user inputs keep their original basis. Read-only observations inform calculations without becoming editable financial facts.</p>
        <div className="assumption-grid">{Object.entries(valuation.assumptionMetadata).map(([field, metadata]) => {
          const unit = metadata.unit;
          const value = metadata.value;
          const suggested = valuation.defaults[valuation.activeScenario]?.metadata?.[field]?.value;
          const display = (input) => typeof input === "boolean" ? String(input) : Array.isArray(input) ? input.map(number).join(", ") : Number.isFinite(input) ? `${number(unit === "fraction" ? input * 100 : input)} ${unit === "fraction" ? "%" : unit || ""}` : "Unavailable";
          return <div className="provider-assumption-record" key={field}><h3>{definitions[field]?.[0] ?? field.replaceAll("_", " ")}</h3>
            <p className="research-caption">Current value: {display(value)} · Suggested: {display(suggested)}</p>
            <ProviderAssumptionSource metadata={metadata} overridden={valuation.overriddenKeys.includes(field)} />
            <p className="research-caption">{metadata.editable === false || !providerEditableAssumptions.has(field) ? "Read-only sourced input" : "Editable modeling assumption"}</p>
          </div>;
        })}</div>
      </details>
    </section>
  );
}
