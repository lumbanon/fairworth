import { Layers3, SlidersHorizontal, GitBranch, FileSearch } from 'lucide-react'

const features = [
  {
    icon: Layers3,
    title: 'Multiple Valuation Models',
    description:
      'Compare intrinsic value estimates using cash flow, earnings, and enterprise value-based valuation methods.',
  },
  {
    icon: SlidersHorizontal,
    title: 'Customizable Assumptions',
    description:
      'Adjust growth rates, discount rates, valuation multiples, and model weights to explore different outcomes.',
  },
  {
    icon: GitBranch,
    title: 'Scenario Analysis',
    description:
      'Evaluate bear, base, and bull cases to understand how changing assumptions affects intrinsic value.',
  },
  {
    icon: FileSearch,
    title: 'Transparent Financial Data',
    description:
      'Review the financial statements, assumptions, and calculation methodologies behind every valuation.',
  },
]

export default function Features() {
  return (
    <section
      id="features"
      className="features-section section container"
      aria-labelledby="features-title"
    >
      <div className="section-intro">
        <p className="eyebrow">BUILT FOR THOUGHTFUL INVESTORS</p>
        <h2 id="features-title">
          More context.
          <br /> Better conviction.
        </h2>
        <p>
          Go beyond a single price target. Understand the assumptions, the
          possibilities, and the reasoning behind value.
        </p>
        <span className="phase-note">
          Planned capabilities · frontend preview
        </span>
      </div>
      <div className="features-grid">
        {features.map(({ icon: Icon, title, description }) => (
          <article className="feature" key={title}>
            <Icon size={20} strokeWidth={1.5} aria-hidden="true" />
            <h3>{title}</h3>
            <p>{description}</p>
          </article>
        ))}
      </div>
    </section>
  )
}
