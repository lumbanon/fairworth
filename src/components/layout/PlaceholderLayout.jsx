import { Link } from 'react-router'
import { ArrowLeft } from 'lucide-react'

export default function PlaceholderLayout({
  title,
  description,
  children,
  label = 'PHASE 1 · FRONTEND PREVIEW',
}) {
  return (
    <div className="container placeholder-page">
      <Link className="back-link" to="/">
        <ArrowLeft size={16} />
        Back to Fairworth
      </Link>
      <p className="eyebrow">{label}</p>
      <h1>{title}</h1>
      <p className="placeholder-description">{description}</p>
      {children}
    </div>
  )
}
