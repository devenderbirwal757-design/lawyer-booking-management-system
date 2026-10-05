import { cn } from 'cn'

import { Badge } from '@/components/ui/badge'

import type {
  AppointmentStatus,
  PaymentStatus,
} from '@/features/booking/schema'

const appointmentStyles: Record<
  AppointmentStatus,
  { label: string; className: string }
> = {
  PENDING_PAYMENT: {
    label: 'Awaiting payment',
    className:
      'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900/40 dark:bg-amber-900/30 dark:text-amber-300',
  },
  CONFIRMED: {
    label: 'Confirmed',
    className:
      'border-green-200 bg-green-50 text-green-800 dark:border-green-900/40 dark:bg-green-900/30 dark:text-green-300',
  },
  COMPLETED: {
    label: 'Completed',
    className:
      'border-blue-200 bg-blue-50 text-blue-800 dark:border-blue-900/40 dark:bg-blue-900/30 dark:text-blue-300',
  },
  CANCELLED: {
    label: 'Cancelled',
    className: 'border-border bg-muted text-muted-foreground dark:bg-muted/40',
  },
  NO_SHOW: {
    label: 'No-show',
    className:
      'border-red-200 bg-red-50 text-red-800 dark:border-red-900/40 dark:bg-red-900/30 dark:text-red-300',
  },
  RESCHEDULED: {
    label: 'Rescheduled',
    className:
      'border-purple-200 bg-purple-50 text-purple-800 dark:border-purple-900/40 dark:bg-purple-900/30 dark:text-purple-300',
  },
  EXPIRED: {
    label: 'Expired',
    className:
      'border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-800 dark:bg-slate-900/40 dark:text-slate-300',
  },
}

export function AppointmentStatusBadge({
  status,
  className,
}: {
  status?: AppointmentStatus
  className?: string
}) {
  if (!status) {
    return null
  }
  const config = appointmentStyles[status] ?? {
    label: status,
    className: 'border-border bg-muted text-muted-foreground dark:bg-muted/40',
  }
  return (
    <Badge variant="default" className={cn(config.className, className)}>
      {config.label}
    </Badge>
  )
}

const paymentStyles: Record<
  PaymentStatus,
  { label: string; className: string }
> = {
  CREATED: {
    label: 'Created',
    className:
      'border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-800 dark:bg-slate-900/40 dark:text-slate-300',
  },
  PENDING: {
    label: 'Pending',
    className:
      'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900/40 dark:bg-amber-900/30 dark:text-amber-300',
  },
  SUCCESS: {
    label: 'Paid',
    className:
      'border-green-200 bg-green-50 text-green-800 dark:border-green-900/40 dark:bg-green-900/30 dark:text-green-300',
  },
  FAILED: {
    label: 'Failed',
    className:
      'border-red-200 bg-red-50 text-red-800 dark:border-red-900/40 dark:bg-red-900/30 dark:text-red-300',
  },
  EXPIRED: {
    label: 'Expired',
    className:
      'border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-800 dark:bg-slate-900/40 dark:text-slate-300',
  },
  CANCELLED: {
    label: 'Cancelled',
    className: 'border-border bg-muted text-muted-foreground dark:bg-muted/40',
  },
  REFUNDED: {
    label: 'Refunded',
    className:
      'border-blue-200 bg-blue-50 text-blue-800 dark:border-blue-900/40 dark:bg-blue-900/30 dark:text-blue-300',
  },
}

export function PaymentStatusBadge({
  status,
  className,
}: {
  status?: PaymentStatus
  className?: string
}) {
  if (!status) {
    return null
  }
  const config = paymentStyles[status] ?? {
    label: status,
    className: 'border-border bg-muted text-muted-foreground dark:bg-muted/40',
  }
  return (
    <Badge variant="default" className={cn(config.className, className)}>
      {config.label}
    </Badge>
  )
}

export const APPOINTMENT_STATUS_LABELS = Object.fromEntries(
  Object.entries(appointmentStyles).map(([status, style]) => [
    status,
    style.label,
  ])
)

export const PAYMENT_STATUS_LABELS = Object.fromEntries(
  Object.entries(paymentStyles).map(([status, style]) => [status, style.label])
)
