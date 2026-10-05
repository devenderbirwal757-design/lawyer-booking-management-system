'use client'

import { useRouter } from 'next/navigation'
import { ClockIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Price } from '@/components/shared/price'
import { cn } from 'cn'

import type { Service } from '@/features/services/schema'
import { useActiveServices } from '@/features/services/api'

interface ServiceStepProps {
  selectedService: Service | null
  onSelect: (service: Service) => void
  onContinue: () => void
}

export function ServiceStep({
  selectedService,
  onSelect,
  onContinue,
}: ServiceStepProps) {
  const router = useRouter()
  const services = useActiveServices()

  const choose = (service: Service) => {
    onSelect(service)
    router.replace(`/book?service=${service.slug}`, { scroll: false })
  }

  if (services.isLoading) {
    return (
      <div className="grid gap-4 sm:grid-cols-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-44 rounded-xl" />
        ))}
      </div>
    )
  }

  if (services.isError || !services.data) {
    return (
      <div className="flex flex-col items-start gap-3 rounded-xl border border-dashed border-border px-4 py-8">
        <p className="text-sm text-muted-foreground">
          We couldn&apos;t load the services right now. Please try again.
        </p>
        <Button onClick={() => void services.refetch()}>Retry</Button>
      </div>
    )
  }

  if (!services.data.results.length) {
    return (
      <div className="flex flex-col items-start gap-3 rounded-xl border border-dashed border-border px-4 py-8">
        <p className="text-sm text-muted-foreground">
          Services are being finalised. Check back shortly.
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 sm:grid-cols-2">
        {services.data.results.map((service) => {
          const active = selectedService?.id === service.id
          return (
            <button
              key={service.id}
              type="button"
              aria-pressed={active}
              onClick={() => choose(service)}
              className={cn(
                'flex flex-col gap-2 rounded-xl border p-5 text-left transition-colors',
                active
                  ? 'border-primary bg-primary/5'
                  : 'border-border bg-card hover:border-primary/50'
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <h3 className="font-medium">{service.name}</h3>
                <Price
                  amount={service.price_amount}
                  currency={service.currency}
                  className="text-sm font-semibold text-primary"
                />
              </div>
              <p className="text-sm text-muted-foreground">
                {service.description}
              </p>
              <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <ClockIcon className="size-3.5" />
                {service.duration_minutes} min · instant confirmation after
                payment
              </p>
            </button>
          )
        })}
      </div>

      <div className="flex justify-end">
        <Button size="lg" disabled={!selectedService} onClick={onContinue}>
          Choose date &amp; time
        </Button>
      </div>
    </div>
  )
}
