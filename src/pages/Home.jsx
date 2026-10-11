import Hero from '@/components/landing/Hero'
import DashboardPreview from '@/components/landing/DashboardPreview'
import Features from '@/components/landing/Features'
import ValuationModels from '@/components/landing/ValuationModels'
import HowItWorks from '@/components/landing/HowItWorks'
import FinalCTA from '@/components/landing/FinalCTA'

export default function Home() {
  return (
    <>
      <Hero />
      <DashboardPreview />
      <Features />
      <ValuationModels />
      <HowItWorks />
      <FinalCTA />
    </>
  )
}
