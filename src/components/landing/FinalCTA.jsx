import { ArrowRight } from 'lucide-react'
import { Link } from 'react-router'
import { Button } from '@/components/ui/button'

export default function FinalCTA() {
  return (
    <section className="cta-section" aria-labelledby="cta-title">
      <div className="container cta-inner">
        <div>
          <p className="eyebrow">MAKE ROOM FOR YOUR OWN PERSPECTIVE</p>
          <h2 id="cta-title">A Clearer Perspective on Value.</h2>
          <p>
            Explore stock valuations through transparent financial models
            <br className="desktop-break" /> and assumptions you control.
          </p>
        </div>
        <Button asChild>
          <Link to="/dashboard">
            Start Analyzing <ArrowRight />
          </Link>
        </Button>
      </div>
    </section>
  )
}
