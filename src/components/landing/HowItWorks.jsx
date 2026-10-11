const steps = [
  {
    title: 'Search',
    description: 'Find a publicly traded US company using its ticker symbol.',
  },
  {
    title: 'Analyze',
    description:
      'Review financial fundamentals and calculate applicable valuation models.',
  },
  {
    title: 'Compare',
    description:
      'Compare intrinsic value estimates and examine different valuation scenarios.',
  },
  {
    title: 'Customize',
    description:
      'Adjust assumptions and explore how changes affect the estimated fair value.',
  },
]

export default function HowItWorks() {
  return (
    <section
      id="how-it-works"
      className="how-section section container"
      aria-labelledby="how-title"
    >
      <p className="eyebrow">FROM CURIOSITY TO CLARITY</p>
      <div className="section-heading-row">
        <h2 id="how-title">A deliberate approach to research.</h2>
        <p>The workflow we’re building, in four simple steps.</p>
      </div>
      <ol className="steps">
        {steps.map((step, index) => (
          <li key={step.title}>
            <span className="step-number">0{index + 1}</span>
            <h3>{step.title}</h3>
            <p>{step.description}</p>
          </li>
        ))}
      </ol>
    </section>
  )
}
