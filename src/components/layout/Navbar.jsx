import { useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router'
import { Menu, X, ArrowUpRight } from 'lucide-react'
import { Button } from '@/components/ui/button'

const links = [
  ['Features', 'features'],
  ['Valuation Models', 'valuation-models'],
  ['How It Works', 'how-it-works'],
]

export default function Navbar() {
  const [open, setOpen] = useState(false)
  const menuRef = useRef(null)
  const toggleRef = useRef(null)
  const location = useLocation()

  useEffect(() => {
    if (!open) return
    function onKey(event) {
      if (event.key === 'Escape') {
        setOpen(false)
        toggleRef.current?.focus()
      }
    }
    function onPointer(event) {
      if (!menuRef.current?.contains(event.target)) setOpen(false)
    }
    const media = window.matchMedia('(min-width: 768px)')
    const onResize = () => {
      if (media.matches) setOpen(false)
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('pointerdown', onPointer)
    media.addEventListener('change', onResize)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('pointerdown', onPointer)
      media.removeEventListener('change', onResize)
    }
  }, [open])

  function closeMenu() {
    setOpen(false)
  }
  return (
    <header className="site-header" ref={menuRef}>
      <div className="container nav-inner">
        <Link
          to="/"
          className="wordmark"
          aria-label="Fairworth home"
          onClick={closeMenu}
        >
          fairworth<span className="wordmark-period">.</span>
        </Link>
        <nav className="desktop-nav" aria-label="Main navigation">
          {links.map(([label, id]) => (
            <Link
              key={id}
              to={`/#${id}`}
              onClick={() => {
                if (location.pathname === '/')
                  document.getElementById(id)?.scrollIntoView()
              }}
            >
              {label}
            </Link>
          ))}
        </nav>
        <div className="nav-actions">
          <Link className="sign-in-link" to="/signin">
            Sign In
          </Link>
          <Button asChild size="sm">
            <Link to="/dashboard">
              Get Started <ArrowUpRight />
            </Link>
          </Button>
        </div>
        <Button
          ref={toggleRef}
          variant="ghost"
          size="icon"
          className="mobile-toggle"
          aria-label={open ? 'Close navigation menu' : 'Open navigation menu'}
          aria-expanded={open}
          aria-controls="mobile-navigation"
          onClick={() => setOpen(!open)}
        >
          {open ? <X /> : <Menu />}
        </Button>
      </div>
      {open && (
        <nav
          className="mobile-nav container"
          id="mobile-navigation"
          aria-label="Mobile navigation"
        >
          {links.map(([label, id]) => (
            <Link key={id} to={`/#${id}`} onClick={closeMenu}>
              {label}
            </Link>
          ))}
          <Link to="/signin" onClick={closeMenu}>
            Sign In
          </Link>
          <Button asChild>
            <Link to="/dashboard" onClick={closeMenu}>
              Get Started <ArrowUpRight />
            </Link>
          </Button>
        </nav>
      )}
    </header>
  )
}
