import { useParams } from 'react-router'
import PlaceholderLayout from '@/components/layout/PlaceholderLayout'

const pages = {
  methodology: {
    title: 'Methodology',
    description:
      'Methodology placeholder. Detailed model documentation and calculation assumptions will be published as valuation capabilities are implemented. Explore the planned valuation methods on the home page.',
  },
  about: {
    title: 'About Fairworth',
    description:
      'Fairworth is being built to help investors examine the intrinsic value of US-listed stocks through multiple appropriate valuation models and transparent assumptions. This Phase 1 release is a frontend preview.',
  },
  privacy: {
    title: 'Privacy Policy',
    description:
      'Privacy Policy placeholder. A complete policy has not been published. This Phase 1 frontend does not implement accounts, analytics, or server-side storage of search input.',
  },
  terms: {
    title: 'Terms of Service',
    description:
      'Terms of Service placeholder. Full terms have not been published. This frontend preview contains fictional demonstration data for informational and educational purposes.',
  },
}

export default function InformationPlaceholder() {
  const { page } = useParams()
  const info = pages[page] || {
    title: 'Page not found',
    description:
      'This page isn’t part of the Fairworth preview. Return to the home page to explore the available sections.',
  }
  return <PlaceholderLayout title={info.title} description={info.description} />
}
