import { Link } from 'react-router'

export default function Footer() {
  return (
    <footer className="site-footer">
      <div className="container">
        <div className="footer-top">
          <div>
            <Link to="/" className="wordmark">
              fairworth<span className="wordmark-period">.</span>
            </Link>
            <p className="footer-tagline">A clearer perspective on value.</p>
          </div>
          <nav className="footer-links" aria-label="Footer navigation">
            <Link to="/#features">Features</Link>
            <Link to="/#valuation-models">Valuation Models</Link>
            <Link to="/#how-it-works">How It Works</Link>
            <Link to="/methodology">Methodology</Link>
            <Link to="/about">About</Link>
            <Link to="/privacy">Privacy Policy</Link>
            <Link to="/terms">Terms of Service</Link>
          </nav>
        </div>
        <div className="footer-bottom">
          <p>
            Fairworth provides model-based financial analysis for informational
            and educational purposes only. Valuation estimates are subject to
            uncertainty and do not constitute personalized investment advice.
          </p>
          <span>© {new Date().getFullYear()} Fairworth</span>
        </div>
      </div>
    </footer>
  )
}
