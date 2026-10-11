import { Link } from 'react-router'
import { ArrowRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import StockSearch from './StockSearch'

export default function Hero() {
  return (
    <section className="hero container" aria-labelledby="hero-title">
      <p className="eyebrow">
        <span className="eyebrow-rule" /> Independent thinking. Informed
        investing.
      </p>
      <h1 id="hero-title">
        Understand What
        <br /> a Stock Is <span>Worth.</span>
      </h1>
      <p className="hero-description">
        Estimate the intrinsic value of US stocks using multiple valuation
        models, transparent financial data, and assumptions you control.
      </p>
      <div className="hero-actions">
        <Button asChild>
          <Link to="/dashboard">
            Analyze a Stock <ArrowRight />
          </Link>
        </Button>
        <Button asChild variant="outline">
          <a href="#valuation-models">Explore Valuation Models</a>
        </Button>
      </div>
      <StockSearch />
    </section>
  )
}
