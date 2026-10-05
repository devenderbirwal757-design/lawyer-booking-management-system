import Link from 'next/link'
import { ArrowRightIcon, CalendarXIcon } from 'lucide-react'

import {
  ServiceCard,
  ServiceCardSkeleton,
} from '@/components/public/service-card'
import { EmptyState } from '@/components/shared/empty-state'
import { Button } from '@/components/ui/button'
import { ServicesResult } from '@/features/services/server-queries'

export function ServicesSection({ result }: { result: ServicesResult }) {
  return (
    <section id="services" className="border-y border-border bg-muted/40">
      <div className="mx-auto w-full max-w-6xl px-4 py-16">
        <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
          <div className="flex flex-col gap-2">
            <p className="text-sm font-medium text-primary">Consultations</p>
            <h2 className="font-serif text-3xl tracking-tight">
              Services &amp; pricing
            </h2>
          </div>
          <Button asChild variant="ghost">
            <Link href="/services">
              See all services <ArrowRightIcon className="size-4" />
            </Link>
          </Button>
        </div>

        {result.ok ? (
          result.services.length ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {result.services.slice(0, 6).map((service) => (
                <ServiceCard key={service.id} service={service} />
              ))}
            </div>
          ) : (
            <EmptyState
              icon={<CalendarXIcon className="size-6" />}
              title="Services are being finalised"
              description="Booking opens shortly. Check back soon or contact us directly to schedule a consultation."
            />
          )
        ) : (
          <EmptyState
            icon={<CalendarXIcon className="size-6" />}
            title="Services are temporarily unavailable"
            description="We couldn't load the service catalogue. Please try again later or reach out directly."
          />
        )}
      </div>
    </section>
  )
}

export function ServicesSectionSkeleton() {
  return (
    <section className="border-y border-border bg-muted/40">
      <div className="mx-auto w-full max-w-6xl px-4 py-16">
        <div className="mb-8 h-8 w-64 animate-pulse rounded bg-muted" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <ServiceCardSkeleton key={i} />
          ))}
        </div>
      </div>
    </section>
  )
}
