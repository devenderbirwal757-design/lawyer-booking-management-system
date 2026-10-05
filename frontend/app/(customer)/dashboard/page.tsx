'use client'

import { format } from 'date-fns'
import {
  AlertCircleIcon,
  ArrowRightIcon,
  CalendarCheck2Icon,
  CalendarClockIcon,
} from 'lucide-react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState } from 'react'

import { AppointmentCard } from '@/components/customer/appointment-card'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/shared/empty-state'
import { Price } from '@/components/shared/price'
import { AppointmentStatusBadge } from '@/components/shared/status-badge'
import { toApiError } from '@/lib/api/error'

import {
  useMeAppointments,
  type AppointmentListStatus,
} from '@/features/portal/api'
import type { AppointmentDetail } from '@/features/portal/schema'

type TabValue = AppointmentListStatus

export default function DashboardPage() {
  const [tab, setTab] = useState<TabValue>('upcoming')
  const upcoming = useMeAppointments('upcoming')
  const past = useMeAppointments('past')
  const cancelled = useMeAppointments('cancelled')

  const queries = { upcoming, past, cancelled }
  const heroAppointment = upcoming.data?.results[0]

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col gap-1">
        <h1 className="font-serif text-2xl font-semibold tracking-tight">
          My Dashboard
        </h1>
        <p className="text-sm text-muted-foreground">
          Manage your consultations, payments, and profile.
        </p>
      </div>

      <HeroCard
        appointment={heroAppointment ?? null}
        loading={upcoming.isLoading}
      />

      <Tabs value={tab} onValueChange={(value) => setTab(value as TabValue)}>
        <TabsList variant="line" className="w-full justify-start">
          <TabsTrigger value="upcoming">
            Upcoming
            {upcoming.data?.count ? ` (${upcoming.data.count})` : ''}
          </TabsTrigger>
          <TabsTrigger value="past">
            Past
            {past.data?.count ? ` (${past.data.count})` : ''}
          </TabsTrigger>
          <TabsTrigger value="cancelled">
            Cancelled
            {cancelled.data?.count ? ` (${cancelled.data.count})` : ''}
          </TabsTrigger>
        </TabsList>

        {(['upcoming', 'past', 'cancelled'] as const).map((status) => (
          <TabsContent key={status} value={status} className="pt-4">
            <AppointmentList query={queries[status]} status={status} />
          </TabsContent>
        ))}
      </Tabs>
    </div>
  )
}

function HeroCard({
  appointment,
  loading,
}: {
  appointment: AppointmentDetail | null
  loading: boolean
}) {
  if (loading) {
    return (
      <div className="grid gap-3 rounded-2xl border border-border bg-card p-6">
        <Skeleton className="h-5 w-40" />
        <Skeleton className="h-9 w-64" />
        <Skeleton className="h-4 w-56" />
      </div>
    )
  }

  if (!appointment) {
    return (
      <div className="rounded-2xl border border-border bg-card p-6">
        <div className="flex flex-col items-start gap-2">
          <p className="flex items-center gap-2 text-sm font-medium text-foreground">
            <CalendarClockIcon className="size-4 text-muted-foreground" />
            No upcoming appointments
          </p>
          <p className="text-sm text-muted-foreground">
            Book a consultation to see it here with all the details.
          </p>
          <Button asChild className="mt-2">
            <Link href="/book">
              Book a consultation
              <ArrowRightIcon className="size-4" />
            </Link>
          </Button>
        </div>
      </div>
    )
  }

  const start = new Date(appointment.start_at)
  const service = appointment.service

  return (
    <Link
      href={`/bookings/${appointment.id}`}
      className="group block rounded-2xl border border-border bg-card p-6 transition-colors hover:border-primary/40"
    >
      <p className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
        <CalendarCheck2Icon className="size-4" />
        Upcoming appointment
        <AppointmentStatusBadge status={appointment.status} />
      </p>
      <p className="mt-3 font-serif text-2xl font-semibold tracking-tight">
        {format(start, 'EEE, d MMM yyyy')}
      </p>
      <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
        <span className="font-medium">{format(start, 'h:mm a')}</span>
        <span className="text-muted-foreground">
          {service.name ?? 'Consultation'}
        </span>
        {typeof service.price_amount === 'number' ? (
          <Price
            amount={service.price_amount}
            currency={service.currency ?? 'INR'}
            className="font-semibold"
          />
        ) : null}
      </p>
      <p className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-primary">
        View details
        <ArrowRightIcon className="size-4 transition-transform group-hover:translate-x-0.5" />
      </p>
    </Link>
  )
}

function AppointmentList({
  query,
  status,
}: {
  query: ReturnType<typeof useMeAppointments>
  status: AppointmentListStatus
}) {
  const router = useRouter()

  if (query.isLoading) {
    return (
      <div className="flex flex-col gap-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-24 rounded-xl" />
        ))}
      </div>
    )
  }

  if (query.isError) {
    return (
      <Alert variant="destructive">
        <AlertCircleIcon />
        <AlertTitle>Could not load your appointments</AlertTitle>
        <AlertDescription>{toApiError(query.error).message}</AlertDescription>
      </Alert>
    )
  }

  const results = query.data?.results ?? []
  if (!results.length) {
    const copy: Record<AppointmentListStatus, string> = {
      upcoming: 'You have no upcoming appointments.',
      past: 'No past consultations yet.',
      cancelled: 'No cancelled bookings.',
    }
    return (
      <EmptyState
        icon={<CalendarCheck2Icon className="size-6" />}
        title={copy[status]}
        description={
          status === 'upcoming'
            ? 'Choose a service and a time to get started.'
            : undefined
        }
        actionLabel={status === 'upcoming' ? 'Book a consultation' : undefined}
        onAction={
          status === 'upcoming' ? () => router.push('/book') : undefined
        }
      />
    )
  }

  return (
    <div className="flex flex-col gap-3">
      {results.map((appointment) => (
        <AppointmentCard key={appointment.id} appointment={appointment} />
      ))}
    </div>
  )
}
