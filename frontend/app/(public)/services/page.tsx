import type { Metadata } from 'next'
import { CalendarXIcon } from 'lucide-react'

import {
  ServiceCard,
  ServiceCardSkeleton,
} from '@/components/public/service-card'
import { EmptyState } from '@/components/shared/empty-state'

import { getActiveServices } from '@/features/services/server-queries'

export const metadata: Metadata = {
  title: 'Services & pricing',
  description:
    'Browse consultation services, durations, and pricing. Book online and get an instant confirmation.',
  alternates: {
    canonical: '/services',
  },
  openGraph: {
    title: 'Services & pricing',
    description:
      'Browse consultation services, durations, and pricing. Book online and get an instant confirmation.',
    url: '/services',
    type: 'website',
  },
}

export default async function ServicesPage() {
  const result = await getActiveServices()

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-12">
      <header className="mb-10 flex max-w-2xl flex-col gap-3">
        <h1 className="font-serif text-4xl tracking-tight">
          Services &amp; pricing
        </h1>
        <p className="text-muted-foreground">
          Every consultation has a fixed duration and price, so you know what to
          expect before you book.
        </p>
      </header>

      {result.ok ? (
        result.services.length ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {result.services.map((service) => (
              <ServiceCard key={service.id} service={service} />
            ))}
          </div>
        ) : (
          <EmptyState
            icon={<CalendarXIcon className="size-6" />}
            title="No services listed yet"
            description="We're setting up the service catalogue. Reach out directly to schedule a consultation."
            actionLabel="Contact us"
          />
        )
      ) : (
        <EmptyState
          icon={<CalendarXIcon className="size-6" />}
          title="Services are temporarily unavailable"
          description={result.error}
        />
      )}
    </div>
  )
}

export function ServicesPageSkeleton() {
  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-12">
      <div className="mb-10 flex flex-col gap-3">
        <div className="h-9 w-64 animate-pulse rounded bg-muted" />
        <div className="h-5 w-96 max-w-full animate-pulse rounded bg-muted" />
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <ServiceCardSkeleton key={i} />
        ))}
      </div>
    </div>
  )
}
