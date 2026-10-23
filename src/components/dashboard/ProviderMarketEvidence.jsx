import { providerAccessLabel, quoteCurrencyLabel, providerQuoteCurrency, marketCapabilities } from "@/lib/marketDataPresentation";
import { providerSourceLinks } from "@/lib/providerDiagnostics";

const endpointLabels = { quote: "Observed quote", profile: "Security profile", "historical-price-eod/full": "Historical prices", dividends: "Dividends", splits: "Share splits", "shares-float": "Share counts", "balance-sheet-statement": "Balance sheet", "cash-flow-statement": "Cash flow" };

export default function ProviderMarketEvidence({ company }) {
  const market = company.market;
  const resolution = market?.currency_resolution;
  const capabilities = marketCapabilities(company);
  const quoteAccess = capabilities?.endpoints?.quote ?? market?.provider_capability;
  const denied = ["requires_paid_subscription", "explicitly_denied"].includes(quoteAccess?.access_status);
  const evidence = Array.isArray(resolution?.evidence) ? resolution.evidence : [];
  return <div className="provider-market-evidence">
    <div className="company-metadata">
      <span data-testid="quote-currency-status">Quote currency: <strong>{providerQuoteCurrency(market) || "Unverified"}</strong> · {quoteCurrencyLabel(resolution)}</span>
      <span>Financial reporting currency: <strong>{company.currency || "Unavailable"}</strong></span>
      <span>Currency compatibility: <strong>{({ compatible: "Compatible", incompatible: "Incompatible", unverified: "Unverified" })[market?.reporting_currency_compatibility?.status] || "Unverified"}</strong></span>
      {quoteAccess && <span data-testid="quote-access-status">Quote access: <strong>{providerAccessLabel(quoteAccess.access_status)}</strong></span>}
    </div>
    {resolution?.status === "quote_currency_unverified" && <p className="research-warning" role="status">The observed price has no verified currency for this exact security. Reporting currency and a US exchange do not establish quote currency; affected market comparisons remain unavailable.</p>}
    {resolution?.status === "conflict" && <p className="research-warning" role="status">Currency source records disagree. The conflicting observations remain inspectable; no currency is selected for a market comparison.</p>}
    {denied && <p className="research-warning" role="status">The required quote data is restricted under the configured provider access. A missing quote is not replaced by a fictional price or fair value.</p>}
    {(resolution || capabilities || quoteAccess) && <details className="research-original-diagnostics" data-testid="market-evidence-details"><summary>Market data access and currency sources</summary>
      {capabilities && <>
        <p>Configured provider: <strong>{capabilities.provider || "Unavailable"}</strong>{capabilities.subscription && <> · Subscription: <strong>{capabilities.subscription}</strong></>}.</p>
        <p className="research-caption">Access observations are dated outcomes for the selected security. A successful request does not guarantee future entitlement or permission for public display.</p>
        <p className="research-caption">Public display rights: {capabilities.display_license_status === "unresolved" ? "Unresolved" : "Not assessed"}.</p>
        <ul className="provider-blocker-list">{Object.entries(capabilities.endpoints ?? {}).map(([key, record]) => <li key={key}><strong>{endpointLabels[key] || key}: {providerAccessLabel(record.access_status)}</strong><p className="research-caption">Observed: {record.observed_at || "No dated access test"}{record.acquisition_authorized === false && " · Live refresh not enabled"}{record.error_code && ` · ${record.error_code.replaceAll("_", " ")}`}</p></li>)}</ul>
      </>}
      {resolution && <>
        <p><strong>Quote currency assessment: </strong>{quoteCurrencyLabel(resolution)}.</p>
        {(resolution.reason_codes ?? []).length > 0 && <p className="research-caption">Assessment reasons: {resolution.reason_codes.map((reason) => reason.replaceAll("_", " ")).join(", ")}.</p>}
        {evidence.map((source, index) => <details className="provider-input-record" key={index}><summary>Currency source {index + 1}: {source.provider || "Provider unavailable"}</summary>
          <dl className="provider-record-metadata">
            <div><dt>Evidence type</dt><dd>{source.source_kind?.replaceAll("_", " ") || "Unavailable"}</dd></div>
            <div><dt>Source version / observation date</dt><dd>{source.source_version_date || "Unavailable"}</dd></div>
            <div><dt>Retrieved</dt><dd>{source.retrieved_at || "Unavailable"}</dd></div>
            <div><dt>Exact listing</dt><dd>{source.listing_id || "Unavailable"}</dd></div>
            <div><dt>Source record hash</dt><dd>{source.source_record_hash || "Unavailable"}</dd></div>
          </dl>
          {providerSourceLinks(source).map((url) => <a key={url} href={url} target="_blank" rel="noreferrer">Original currency source</a>)}
          <details className="research-original-diagnostics"><summary>Exact currency evidence record</summary><pre>{JSON.stringify(source, null, 2)}</pre></details>
        </details>)}
      </>}
    </details>}
    <details className="research-original-diagnostics" data-testid="ibkr-personal-use-status"><summary>Optional IBKR personal research</summary><p>IBKR is not connected through this website. Its optional local tool requires separate connection approval, compatible API subscriptions and applicable non-display permissions.</p><p className="research-caption">Personally subscribed quotes and derived results stay in local research. Public mode does not publish IBKR data or provide trading access.</p></details>
  </div>;
}
