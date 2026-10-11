import { useState } from 'react'
import { Info } from 'lucide-react'
import { valuationModels } from '@/data/valuationModels'

const categories = [
  'All models',
  'Cash flow',
  'Multiples',
  'Equity & income',
  'Specialized',
]

export default function ValuationModels() {
  const [category, setCategory] = useState('All models')
  const visibleModels = valuationModels.filter(
    (model) => category === 'All models' || model.category === category,
  )

  return (
    <section
      id="valuation-models"
      className="models-section section"
      aria-labelledby="models-title"
    >
      <div className="container">
        <div className="section-heading-row">
          <div>
            <p className="eyebrow">THE RIGHT MODEL FOR THE RIGHT BUSINESS</p>
            <h2 id="models-title">Value has more than one lens.</h2>
          </div>
          <p>
            A considered toolkit of valuation methods,
            <br className="desktop-break" /> built around how a business creates
            value.
          </p>
        </div>
        <div className="model-filter-row">
          <div
            className="model-filters"
            role="group"
            aria-label="Filter valuation models"
          >
            {categories.map((item) => (
              <button
                key={item}
                aria-pressed={category === item}
                className={category === item ? 'active' : ''}
                onClick={() => setCategory(item)}
              >
                {item}
              </button>
            ))}
          </div>
          <span className="model-count" aria-live="polite">
            {visibleModels.length} methods · planned
          </span>
        </div>
        <p className="table-scroll-hint">
          Scroll horizontally to compare approaches and suitability.
        </p>
        <div
          className="models-table-wrap"
          tabIndex={0}
          role="region"
          aria-label="Planned valuation methods table"
        >
          <table className="models-table">
            <thead>
              <tr>
                <th scope="col">Valuation method</th>
                <th scope="col">Approach</th>
                <th scope="col">Best suited for</th>
              </tr>
            </thead>
            <tbody>
              {visibleModels.map((model) => (
                <tr key={model.name}>
                  <th scope="row">{model.name}</th>
                  <td>{model.description}</td>
                  <td>{model.suitability}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="methodology-note">
          <Info size={17} aria-hidden="true" />
          <p>
            Not every valuation method is appropriate for every company.
            Fairworth selects applicable models based on financial
            characteristics and data availability.{' '}
            <span>
              Combining estimates does not remove uncertainty or guarantee
              accuracy.
            </span>
          </p>
        </div>
      </div>
    </section>
  )
}
