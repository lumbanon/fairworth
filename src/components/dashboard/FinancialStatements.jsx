import { useState } from "react";
import {
  dollars,
  totalDollars,
  number,
  percent,
} from "@/lib/financialFormatting";

const statements = {
  income: {
    label: "Income Statement",
    rows: [
      ["Revenue", "revenue"],
      ["Revenue growth", "revenueGrowth", "percent"],
      ["Gross profit", "grossProfit"],
      ["Operating income", "operatingIncome"],
      ["Net income", "netIncome"],
      ["Diluted EPS", "eps", "perShare"],
      ["Diluted shares (million)", "shares", "number"],
    ],
  },
  balance: {
    label: "Balance Sheet",
    rows: [
      ["Cash and equivalents", "cash"],
      ["Total debt", "debt"],
      ["Total assets", "assets"],
      ["Total liabilities", "liabilities"],
      ["Shareholders’ equity", "bookEquity"],
    ],
  },
  cash: {
    label: "Cash Flow Statement",
    rows: [
      ["Operating cash flow", "operatingCashFlow"],
      ["Capital expenditures (outflow)", "capex"],
      ["Free cash flow / FCFE proxy", "freeCashFlow"],
      ["After-tax interest adjustment", "afterTaxInterest"],
      ["FCFF proxy", "fcff"],
      ["Dividends paid", "dividends"],
      ["AFFO (REIT only)", "affo"],
    ],
  },
};

function DemoFinancialStatements({ company }) {
  const [active, setActive] = useState("income");
  const years = company.financials.map((year, index) => ({
    ...year,
    revenueGrowth:
      index === 0
        ? null
        : (year.revenue / company.financials[index - 1].revenue - 1) * 100,
    afterTaxInterest: year.interestExpense * 0.79,
  }));
  const statement = statements[active];
  const rows = statement.rows.filter(([, key]) =>
    years.some((year) => year[key] != null),
  );
  return (
    <section
      id="financials"
      className="research-section"
      aria-labelledby="financials-heading"
    >
      <div className="research-section-heading">
        <div>
          <h2 id="financials-heading">Financial fundamentals</h2>
          <p>
            Three fictional fiscal years. Historical statements stay fixed when
            forward assumptions change.
          </p>
        </div>
        <span className="research-caption">
          Annual data · Quarterly data unavailable
        </span>
      </div>
      <div
        className="research-segmented statement-tabs"
        role="group"
        aria-label="Financial statement"
      >
        {Object.entries(statements).map(([key, value]) => (
          <button
            key={key}
            aria-pressed={active === key}
            onClick={() => setActive(key)}
          >
            {value.label}
          </button>
        ))}
      </div>
      <div
        className="research-table-scroll"
        tabIndex={0}
        role="region"
        aria-label={statement.label}
      >
        <table className="research-table statements-table">
          <caption>{statement.label} · Mock financial data</caption>
          <thead>
            <tr>
              <th scope="col">Financial metric</th>
              {years.map((year) => (
                <th key={year.year} scope="col">
                  FY {year.year}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(([label, key, unit]) => (
              <tr key={key}>
                <th scope="row">{label}</th>
                {years.map((year) => (
                  <td key={year.year}>
                    {unit === "percent"
                      ? percent(year[key])
                      : unit === "perShare"
                        ? dollars(year[key])
                        : unit === "number"
                          ? number(year[key])
                          : totalDollars(year[key])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="research-caption">
        Monetary totals shown in USD millions / billions; EPS in USD per share.
        FCF = operating cash flow − capex. FCFE assumes no net borrowing; FCFF
        adds interest × (1 − 21% demo tax rate). These proxies simplify working
        capital and financing.
      </p>
    </section>
  );
}

const providerStatements = {
  income: {
    label: "Income Statement",
    rows: [
      ["Revenue", "revenue"],
      ["Revenue growth", "revenueGrowth", "percent"],
      ["Cost of revenue", "costOfRevenue"],
      ["Gross profit", "grossProfit"],
      ["Gross margin", "grossMargin", "percent"],
      ["Operating income", "operatingIncome"],
      ["Operating margin", "operatingMargin", "percent"],
      ["Pretax income", "pretaxIncome"],
      ["Income tax expense", "incomeTaxExpense"],
      ["Net income", "netIncome"],
      ["Net profit margin", "netProfitMargin", "percent"],
      ["Basic EPS", "basicEPS", "perShare"],
      ["Diluted EPS", "eps", "perShare"],
      ["Diluted weighted shares (million)", "shares", "number"],
      ["Historical EPS growth", "historicalEPSGrowth", "percent"],
    ],
  },
  balance: {
    label: "Balance Sheet",
    rows: [
      ["Cash and equivalents", "cash"],
      ["Short-term investments", "shortTermInvestments"],
      ["Total current assets", "currentAssets"],
      ["Short-term debt", "shortTermDebt"],
      ["Long-term debt", "longTermDebt"],
      ["Total debt", "debt"],
      ["Total assets", "assets"],
      ["Total liabilities", "liabilities"],
      ["Shareholders’ equity", "bookEquity"],
      ["Net debt", "netDebt"],
      ["Debt-to-equity", "debtToEquity", "multiple"],
      ["Return on average equity", "reportedROE", "percent"],
      ["Point-in-time shares (million)", "sharesOutstanding", "number"],
    ],
  },
  cash: {
    label: "Cash Flow Statement",
    rows: [
      ["Operating cash flow", "operatingCashFlow"],
      ["Capital expenditures (outflow)", "capex"],
      ["Free cash flow", "freeCashFlow"],
      ["Free cash flow margin", "freeCashFlowMargin", "percent"],
      [
        "Historical free cash flow growth",
        "historicalFreeCashFlowGrowth",
        "percent",
      ],
      ["Depreciation and amortization", "depreciation"],
      ["Dividends paid", "dividends"],
      ["Share repurchases", "repurchases"],
    ],
  },
};

function providerMoney(value, currency, compact = false) {
  if (!Number.isFinite(value)) return "—";
  if (!/^[A-Z]{3}$/.test(currency ?? ""))
    return `${number(value)} (currency unavailable)`;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
    ...(compact ? { notation: "compact" } : {}),
  }).format(value);
}

function ProviderFinancialStatements({ company }) {
  const [active, setActive] = useState("income");
  const [selection, setSelection] = useState(
    company.financials.length ? "annual" : "quarterly",
  );
  const years =
    selection === "annual" ? company.financials : company.quarterlyFinancials;
  const statement = providerStatements[active];
  return (
    <section
      id="financials"
      className="research-section"
      aria-labelledby="financials-heading"
    >
      <div className="research-section-heading">
        <div>
          <h2 id="financials-heading">Financial fundamentals</h2>
          <p>
            Normalized SEC financial statements. Missing reported values remain
            unavailable; edited assumptions do not alter these statements.
          </p>
        </div>
        <span className="research-caption">
          {company.currency || "Currency unavailable"} · reported period dates
          below
        </span>
      </div>
      <div className="research-period-controls">
        <div
          className="research-segmented statement-tabs"
          role="group"
          aria-label="Financial statement"
        >
          {Object.entries(providerStatements).map(([key, value]) => (
            <button
              key={key}
              aria-pressed={active === key}
              onClick={() => setActive(key)}
            >
              {value.label}
            </button>
          ))}
        </div>
        <div
          className="research-segmented"
          role="group"
          aria-label="Reporting period"
        >
          {company.financials.length > 0 && (
            <button
              aria-pressed={selection === "annual"}
              onClick={() => setSelection("annual")}
            >
              Annual
            </button>
          )}
          {company.quarterlyFinancials.length > 0 && (
            <button
              aria-pressed={selection === "quarterly"}
              onClick={() => setSelection("quarterly")}
            >
              Quarterly
            </button>
          )}
        </div>
      </div>
      {!years.length ? (
        <p className="research-unavailable">
          No compatible financial statement periods are available from the
          source.
        </p>
      ) : (
        <>
          <div
            className="research-table-scroll"
            tabIndex={0}
            role="region"
            aria-label={statement.label}
          >
            <table className="research-table statements-table">
              <caption>
                {statement.label} · SEC EDGAR · {selection}
              </caption>
              <thead>
                <tr>
                  <th scope="col">Financial metric</th>
                  {years.map((year) => (
                    <th
                      key={`${year.periodEnd}-${year.fiscalPeriod}`}
                      scope="col"
                    >
                      {year.fiscalPeriod || "Reported"} {year.year}
                      <span className="statement-period-date">
                        {year.periodEnd}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {statement.rows.map(([label, key, unit]) => (
                  <tr key={key}>
                    <th scope="row">{label}</th>
                    {years.map((year) => (
                      <td key={`${year.periodEnd}-${year.fiscalPeriod}`}>
                        {unit === "percent"
                          ? percent(year[key])
                          : unit === "multiple"
                            ? Number.isFinite(year[key])
                              ? `${number(year[key])}×`
                              : "—"
                            : unit === "number"
                              ? number(year[key])
                              : providerMoney(
                                  unit === "perShare"
                                    ? year[key]
                                    : Number.isFinite(year[key])
                                      ? year[key] * 1e6
                                      : null,
                                  company.currency,
                                  unit !== "perShare",
                                )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <details className="research-financial-provenance">
            <summary>Reporting periods and original SEC observations</summary>
            {years.map((year) => (
              <div key={`${year.periodEnd}-${year.fiscalPeriod}`}>
                <strong>
                  {year.fiscalPeriod} {year.year} ·{" "}
                  {year.periodStart || "Point-in-time"} – {year.periodEnd}
                </strong>
                <ul>
                  {Object.entries(year.provenance).map(
                    ([metric, observations]) => (
                      <li key={metric}>
                        <strong>{metric}</strong>
                        {(Array.isArray(observations)
                          ? observations
                          : [observations]
                        ).map((observation, index) => (
                          <span key={index}>
                            {observation.concept ??
                              observation.original_concept ??
                              "Derived from source observations"}{" "}
                            ·{" "}
                            {number(
                              observation.reported_value ?? observation.value,
                            )}{" "}
                            {observation.unit ?? ""} · filed{" "}
                            {observation.filing_date ??
                              observation.filed ??
                              "unavailable"}{" "}
                            · accession{" "}
                            {observation.accession_number ??
                              observation.accession ??
                              observation.accn ??
                              "unavailable"}
                          </span>
                        ))}
                      </li>
                    ),
                  )}
                </ul>
              </div>
            ))}
          </details>
        </>
      )}
      <p className="research-caption">
        Monetary totals shown in reported currency millions / billions; EPS
        retains reported per-share units. Weighted diluted shares and
        point-in-time shares have different reporting bases. Annual inputs alone
        feed the Phase 2 valuation engine.{" "}
        {company.quarterlyFinancials.length
          ? "Quarterly statements use compatible standalone source periods."
          : "Quarterly data is unavailable."}{" "}
        FCF requires sourced operating cash flow and capex; no FCFF or FCFE
        demonstration proxies are applied.
      </p>
    </section>
  );
}

export default function FinancialStatements({ company }) {
  return company.dataMode === "provider" ? (
    <ProviderFinancialStatements company={company} />
  ) : (
    <DemoFinancialStatements company={company} />
  );
}
