'use client'

import { useCallback, useEffect, useState } from 'react'
import { Loader2Icon, ShieldCheckIcon } from 'lucide-react'

import { HoldBanner } from '@/components/booking/hold-banner'
import { Button } from '@/components/ui/button'
import { Price } from '@/components/shared/price'
import { ApiError } from '@/lib/api/error'
import { displayDate, displaySlotTime } from '@/lib/utils/dates'

import {
  cancelAppointment,
  createAppointment,
  createPaymentOrder,
  pollAppointmentUntilConfirmed,
} from '@/features/booking/api'
import type {
  Appointment,
  BookingDetails,
  PaymentOrder,
} from '@/features/booking/schema'
import type { Service } from '@/features/services/schema'
import { openRazorpay } from '@/lib/payments/razorpay'

interface PaymentStepProps {
  service: Service
  details: BookingDetails
  date: string
  startAt: string
  idempotencyKey: string
  appointment: Appointment | null
  paymentOrder: PaymentOrder | null
  onAppointmentCreated: (appointment: Appointment) => void
  onOrderCreated: (order: PaymentOrder) => void
  onConfirmed: (appointment: Appointment) => void
  onSlotTaken: () => void
  onHoldExpired: () => void
  onHeldCancelled: () => void
  onBack: () => void
}

type Phase =
  'ready' | 'creating' | 'checkout' | 'verifying' | 'error' | 'unrecoverable'

const RAZORPAY_PUBLISHABLE_KEY =
  process.env.NEXT_PUBLIC_RAZORPAY_KEY_ID ??
  process.env.NEXT_PUBLIC_RAZORPAY_KEY ??
  ''

export function PaymentStep({
  service,
  details,
  date,
  startAt,
  idempotencyKey,
  appointment,
  paymentOrder,
  onAppointmentCreated,
  onOrderCreated,
  onConfirmed,
  onSlotTaken,
  onHoldExpired,
  onHeldCancelled,
  onBack,
}: PaymentStepProps) {
  const [phase, setPhase] = useState<Phase>('ready')
  const [error, setError] = useState<string | null>(null)
  const [cancelling, setCancelling] = useState(false)

  const startAtIso = useCallback(
    () => new Date(`${date}T${startAt}`).toISOString(),
    [date, startAt]
  )

  const openCheckout = useCallback(
    async (appt: Appointment, order: PaymentOrder) => {
      setError(null)
      setPhase('checkout')
      try {
        const instance = await openRazorpay({
          key:
            order.gateway_key_id ??
            order.key_id ??
            RAZORPAY_PUBLISHABLE_KEY,
          // Razorpay expects paise. The API now returns `amount_minor`; fall back
          // to `amount` only if minor units are absent (older shape).
          amount: order.amount_minor ?? order.amount,
          currency: order.currency,
          name: service.name,
          description: `${service.name} · ${displayDate(date)} ${displaySlotTime(startAt)}`,
          order_id: order.gateway_order_id,
          prefill: {
            name: details.name,
            contact: `+91${details.phone}`,
            email: details.email || undefined,
          },
          handler: async () => {
            setPhase('verifying')
            try {
              const confirmed = await pollAppointmentUntilConfirmed(appt.id)
              onConfirmed(confirmed)
            } catch {
              setError(
                "Your payment went through but we couldn't confirm it instantly. We'll email you once it's verified."
              )
              setPhase('unrecoverable')
            }
          },
          modal: {
            ondismiss: () => setPhase('checkout'),
          },
        })
        setError(null)
        instance.open()
      } catch {
        setError(
          'Could not open the payment window. Your slot is still reserved — please retry.'
        )
        setPhase('checkout')
      }
    },
    [date, startAt, details, service, onConfirmed]
  )

  useEffect(() => {
    setPhase('creating')

    const createHold = async (): Promise<Appointment> => {
      if (appointment?.id) {
        return appointment
      }
      return createAppointment(
        {
          service_id: service.id,
          start_at: startAtIso(),
          customer_notes: details.notes || undefined,
        },
        idempotencyKey
      )
    }

    const createOrder = async (appt: Appointment): Promise<PaymentOrder> => {
      if (paymentOrder?.gateway_order_id) {
        return paymentOrder
      }
      const order = await createPaymentOrder({ appointment_id: appt.id })
      onOrderCreated(order)
      return order
    }

    void (async () => {
      try {
        const appt = await createHold()
        onAppointmentCreated(appt)
        const order = await createOrder(appt)
        void openCheckout(appt, order)
      } catch (err) {
        if (err instanceof ApiError && err.isSlotUnavailable) {
          onSlotTaken()
          return
        }
        setError(
          "We couldn't reserve your time. Please try again — your details are saved."
        )
        setPhase('error')
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleCancelHold = async () => {
    if (!appointment?.id) {
      return
    }
    setCancelling(true)
    try {
      await cancelAppointment(appointment.id)
      onHeldCancelled()
    } catch {
      setCancelling(false)
      setError("We couldn't release the hold. Please try again.")
    }
  }

  const renderPhase = () => {
    switch (phase) {
      case 'creating':
        return (
          <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
            <Loader2Icon className="size-4 animate-spin" />
            Reserving your slot…
          </div>
        )
      case 'checkout':
        return (
          <div className="flex flex-col gap-2">
            <p className="text-sm text-muted-foreground">
              Complete the payment in the{' '}
              <button
                className="text-primary underline underline-offset-4"
                onClick={() => {
                  if (appointment && paymentOrder) {
                    void openCheckout(appointment, paymentOrder)
                  }
                }}
              >
                payment window
              </button>{' '}
              to confirm your booking.
            </p>
            <div className="flex flex-wrap gap-2">
              <Button
                variant="outline"
                onClick={() => {
                  if (appointment && paymentOrder) {
                    void openCheckout(appointment, paymentOrder)
                  }
                }}
              >
                Pay again
              </Button>
              <Button
                variant="ghost"
                disabled={cancelling}
                onClick={() => void handleCancelHold()}
              >
                {cancelling ? 'Releasing…' : 'Cancel (release slot)'}
              </Button>
            </div>
          </div>
        )
      case 'verifying':
        return (
          <div className="flex items-center justify-center gap-2 py-6 text-sm">
            <Loader2Icon className="size-4 animate-spin text-primary" />
            Verifying your payment…
          </div>
        )
      case 'unrecoverable':
        return (
          <p className="rounded-xl border border-amber-600/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-800">
            {error}
          </p>
        )
      default:
        return (
          <div className="flex flex-col gap-3">
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
            <div className="flex gap-2">
              <Button onClick={onBack}>Choose a different time</Button>
              <Button variant="ghost" onClick={() => void handleCancelHold()}>
                Cancel
              </Button>
            </div>
          </div>
        )
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <HoldBanner
        expiresAt={appointment?.slot_hold_expires_at ?? null}
        onExpired={onHoldExpired}
      />

      <div className="flex flex-col gap-4 rounded-xl border border-border bg-card p-5">
        <div className="flex items-start justify-between gap-4">
          <div className="flex flex-col gap-1">
            <h3 className="font-medium">{service.name}</h3>
            <p className="text-sm text-muted-foreground">
              {displayDate(date)} at {displaySlotTime(startAt)} · {details.name}
            </p>
          </div>
          <Price
            amount={service.price_amount}
            currency={service.currency}
            className="text-lg font-semibold text-primary"
          />
        </div>

        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <ShieldCheckIcon className="size-3.5" />
          Payment is processed securely by our payment partner.
        </p>
      </div>

      {renderPhase()}
    </div>
  )
}
