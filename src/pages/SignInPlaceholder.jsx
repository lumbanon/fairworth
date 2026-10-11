import { Link } from 'react-router'
import { Button } from '@/components/ui/button'
import PlaceholderLayout from '@/components/layout/PlaceholderLayout'

export default function SignInPlaceholder() {
  return (
    <PlaceholderLayout
      title="Sign in is coming later."
      description="Sign In placeholder. Authentication and user accounts are not implemented in Phase 1. You can explore the frontend preview without an account."
    >
      <Button asChild>
        <Link to="/dashboard">Explore the Preview</Link>
      </Button>
    </PlaceholderLayout>
  )
}
