import Link from 'next/link'
import { ArrowRightIcon, Clock3Icon } from 'lucide-react'

import { Price } from '@/components/shared/price'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Service } from '@/features/services/schema'
import { formatDuration } from '@/lib/utils/money'

export function ServiceCard({ service }: { service: Service }) {
  return (
    <Link href={`/services/${service.slug}`} className="group block h-full">
      <Card className="h-full transition-colors hover:border-ring">
        <CardHeader>
          <CardTitle className="flex items-start justify-between gap-3">
            <span className="font-serif text-lg">{service.name}</span>
          </CardTitle>
          <CardDescription className="line-clamp-3">
            {service.description}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex items-center justify-between gap-3">
          <div className="flex flex-col gap-1">
            <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
              <Clock3Icon className="size-3.5" />
              {formatDuration(service.duration_minutes)}
            </span>
            <Price
              amount={service.price_amount}
              currency={service.currency}
              className="text-lg font-semibold"
            />
          </div>
          <span className="inline-flex items-center gap-1 text-sm font-medium text-primary opacity-0 transition-opacity group-hover:opacity-100">
            Details <ArrowRightIcon className="size-4" />
          </span>
        </CardContent>
      </Card>
    </Link>
  )
}

export function ServiceCardSkeleton() {
  return (
    <Card className="h-full">
      <CardHeader className="gap-2">
        <div className="h-5 w-2/3 animate-pulse rounded bg-muted" />
        <div className="h-4 w-full animate-pulse rounded bg-muted" />
        <div className="h-4 w-4/5 animate-pulse rounded bg-muted" />
      </CardHeader>
      <CardContent className="flex items-center gap-2">
        <div className="h-8 w-16 animate-pulse rounded bg-muted" />
        <div className="h-8 w-20 animate-pulse rounded bg-muted" />
      </CardContent>
    </Card>
  )
}
