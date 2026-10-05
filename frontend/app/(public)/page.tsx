import type { Metadata } from 'next'

import { ContactSection } from '@/components/public/contact'
import { Cta } from '@/components/public/cta'
import { Faq } from '@/components/public/faq'
import { Hero } from '@/components/public/hero'
import { PracticeAreas } from '@/components/public/practice-areas'
import { ServicesSection } from '@/components/public/services-section'
import { JsonLd } from '@/components/shared/json-ld'
import { siteConfig } from '@/lib/constants/site'

import { getActiveServices } from '@/features/services/server-queries'

export const metadata: Metadata = {
  alternates: { canonical: '/' },
}

export default async function LandingPage() {
  const result = await getActiveServices()

  const personJsonLd = {
    '@context': 'https://schema.org',
    '@type': 'ProfessionalService',
    name: siteConfig.name,
    description: siteConfig.description,
    url: siteConfig.url,
    areaServed: 'IN',
    priceRange: '₹300–₹1,000',
    makesOffer: siteConfig.practiceAreas.map((area) => ({
      '@type': 'Offer',
      itemOffered: {
        '@type': 'Service',
        name: area.title,
        description: area.description,
      },
    })),
  }

  return (
    <>
      <JsonLd data={personJsonLd} />
      <Hero />
      <PracticeAreas />
      <ServicesSection result={result} />
      <Cta />
      <Faq />
      <ContactSection />
    </>
  )
}
