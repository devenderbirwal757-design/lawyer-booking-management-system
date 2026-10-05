import type { Metadata } from 'next'
import Link from 'next/link'
import { notFound } from 'next/navigation'
import { Clock3Icon, CalendarPlusIcon } from 'lucide-react'

import { JsonLd } from '@/components/shared/json-ld'
import { Price } from '@/components/shared/price'
import { Button } from '@/components/ui/button'
import { siteConfig } from '@/lib/constants/site'
import { formatDuration } from '@/lib/utils/money'

import { getServiceBySlug } from '@/features/services/server-queries'

interface ServicePageProps {
  params: Promise<{ slug: string }>
}

export async function generateMetadata({
  params,
}: ServicePageProps): Promise<Metadata> {
  const { slug } = await params
  const result = await getServiceBySlug(slug)

  if (result.status !== 'ok') {
    return {
      title: result.status === 'not_found' ? 'Service not found' : 'Services',
      robots: { index: false, follow: true },
    }
  }

  return {
    title: result.service.name,
    description: result.service.description,
    alternates: {
      canonical: `/services/${result.service.slug}`,
    },
    openGraph: {
      title: result.service.name,
      description: result.service.description,
      url: `/services/${result.service.slug}`,
      type: 'website',
    },
  }
}

export default async function ServicePage({ params }: ServicePageProps) {
  const { slug } = await params
  const result = await getServiceBySlug(slug)

  if (result.status === 'not_found') {
    notFound()
  }

  if (result.status !== 'ok') {
    return (
      <div className="mx-auto w-full max-w-6xl px-4 py-12">
        <p className="text-sm text-muted-foreground">
          We couldn&apos;t load this service right now. Please try again
          shortly.
        </p>
      </div>
    )
  }

  const { service } = result

  const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'Service',
    name: service.name,
    description: service.description,
    provider: {
      '@type': 'ProfessionalService',
      name: siteConfig.name,
    },
    offers: {
      '@type': 'Offer',
      price: service.price_amount,
      priceCurrency: service.currency,
    },
    serviceType: service.name,
  }

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-12">
      <JsonLd data={jsonLd} />

      <Link
        href="/services"
        className="text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        ← All services
      </Link>

      <header className="mt-4 flex flex-col gap-3">
        <h1 className="font-serif text-4xl tracking-tight">{service.name}</h1>
        <p className="text-lg text-muted-foreground">{service.description}</p>
      </header>

      <dl className="mt-8 grid gap-4 sm:grid-cols-3">
        <div className="flex flex-col gap-1 rounded-xl border border-border bg-card p-5">
          <dt className="flex items-center gap-2 text-sm text-muted-foreground">
            <Clock3Icon className="size-4" />
            Duration
          </dt>
          <dd className="text-xl font-semibold">
            {formatDuration(service.duration_minutes)}
          </dd>
        </div>
        <div className="flex flex-col gap-1 rounded-xl border border-border bg-card p-5">
          <dt className="text-sm text-muted-foreground">Consultation fee</dt>
          <dd className="text-xl font-semibold">
            <Price amount={service.price_amount} currency={service.currency} />
          </dd>
        </div>
        <div className="flex flex-col gap-1 rounded-xl border border-border bg-card p-5">
          <dt className="text-sm text-muted-foreground">Who it&apos;s for</dt>
          <dd className="text-xl font-semibold">
            Individuals &amp; businesses
          </dd>
        </div>
      </dl>

      <div className="mt-8 flex flex-wrap gap-3">
        <Button asChild size="lg">
          <Link href={`/book?service=${service.slug}`}>
            Book this consultation <CalendarPlusIcon className="size-4" />
          </Link>
        </Button>
        <Button asChild size="lg" variant="outline">
          <Link href="/#faq">Read the booking FAQ</Link>
        </Button>
      </div>

      <div className="mt-12 flex flex-col gap-4 rounded-xl border border-border bg-muted/40 p-6">
        <h2 className="font-serif text-xl">After you book</h2>
        <p className="text-sm text-muted-foreground">
          You pick a date and time that works for you, verify your phone, and
          pay securely online. You&apos;ll receive a confirmation immediately,
          and can manage or reschedule the appointment from the client portal.
        </p>
      </div>
    </div>
  )
}
