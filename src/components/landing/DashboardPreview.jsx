import { lazy, Suspense } from 'react'
import { ArrowUpRight, Info } from 'lucide-react'
import { demoValuation as data } from '@/data/mockStocks'
import { formatCurrency } from '@/lib/format'

const ScenarioChart = lazy(() => import('./ScenarioChart'))

export default function DashboardPreview() {
  return (
    <section
      className="preview-section container"
      aria-labelledby="preview-title"
    >
      <div className="preview-caption">
        <span>A LOOK INSIDE FAIRWORTH</span>
        <span>Clarity, from every angle.</span>
      </div>
      <div className="dashboard-preview">
        <div className="preview-toolbar">
          <span className="preview-product">
            fairworth<span>.</span> <span className="preview-divider" />{' '}
            <span className="toolbar-label">Valuation overview</span>
          </span>
          <span className="demo-label">Demo workspace</span>
        </div>
        <div className="preview-body">
          <div className="company-heading">
            <div className="company-identity">
              <div className="ms-logo" aria-hidden="true">
                <i />
                <i />
                <i />
                <i />
              </div>
              <div>
                <h2 id="preview-title">{data.company}</h2>
                <p>
                  {data.ticker}
                  <span>·</span>
                  {data.exchange}
                  <span>·</span>Technology
                </p>
              </div>
            </div>
            <span className="currency-label">USD · per share</span>
          </div>
          <div className="financial-summary">
            <div className="financial-stat">
              <span>Illustrative market price</span>
              <strong>{formatCurrency(data.marketPrice)}</strong>
              <small>Fictional reference price</small>
            </div>
            <div className="financial-stat fair-value">
              <span>Estimated fair value</span>
              <strong>{formatCurrency(data.fairValue)}</strong>
              <small>Illustrative weighted estimate</small>
            </div>
            <div className="financial-stat">
              <span>Potential upside</span>
              <strong className="positive">
                <ArrowUpRight size={23} />
                {data.upside.toFixed(1)}%
              </strong>
              <small>Relative to reference price</small>
            </div>
            <div className="financial-stat">
              <span>Margin of safety</span>
              <strong>{data.marginOfSafety.toFixed(1)}%</strong>
              <small>Below estimated fair value</small>
            </div>
          </div>
          <div className="dashboard-detail-grid">
            <div className="model-comparison">
              <div className="panel-heading">
                <h3>Valuation model comparison</h3>
                <span>4 illustrative models</span>
              </div>
              <div
                className="comparison-table-wrap"
                tabIndex={0}
                role="region"
                aria-label="Valuation model comparison table"
              >
                <table className="comparison-table">
                  <thead>
                    <tr>
                      <th scope="col">Model</th>
                      <th scope="col">Fair value</th>
                      <th scope="col">Weight</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.models.map((model) => (
                      <tr key={model.name}>
                        <th scope="row">
                          <span>{model.name}</span>
                          <div className="model-bar-track" aria-hidden="true">
                            <div
                              className="model-bar"
                              style={{ width: `${(model.value / 580) * 100}%` }}
                            />
                          </div>
                        </th>
                        <td>{formatCurrency(model.value)}</td>
                        <td>{model.weight}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="panel-note">
                <span className="reference-line" /> Reference market price:{' '}
                {formatCurrency(data.marketPrice)}
              </p>
            </div>
            <div className="scenario-panel">
              <div className="panel-heading">
                <h3>Scenario analysis</h3>
                <span>Fair value / share</span>
              </div>
              <div
                className="scenario-chart"
                role="img"
                aria-label="Illustrative scenario fair values: Bear $365, Base $485, Bull $580. Dashed reference market price: $420."
              >
                <Suspense
                  fallback={
                    <div className="chart-loading">
                      Loading scenario comparison…
                    </div>
                  }
                >
                  <ScenarioChart />
                </Suspense>
              </div>
              <div className="scenario-values">
                {data.scenarios.map((scenario) => (
                  <div key={scenario.name}>
                    <span>
                      <i style={{ background: scenario.color }} />
                      {scenario.name} Case
                    </span>
                    <strong>{formatCurrency(scenario.value)}</strong>
                    <small
                      className={
                        scenario.name === 'Bear' ? 'negative' : 'positive'
                      }
                    >
                      {scenario.change}
                    </small>
                  </div>
                ))}
              </div>
              <div className="fair-value-range">
                <span>Fair value range</span>
                <strong>$365.00 – $580.00</strong>
              </div>
            </div>
          </div>
        </div>
        <div className="demo-disclaimer">
          <Info size={14} aria-hidden="true" />
          <span>
            Illustrative data — not live market prices or actual valuations.
          </span>
        </div>
      </div>
      <p className="preview-footnote">
        A price is a number. A valuation is a perspective.
      </p>
    </section>
  )
}
