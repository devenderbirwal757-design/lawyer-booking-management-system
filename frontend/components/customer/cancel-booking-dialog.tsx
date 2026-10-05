'use client'

import { useState } from 'react'
import { toast } from 'sonner'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

import { formatMoney } from '@/lib/utils/money'
import { toApiError } from '@/lib/api/error'

import { useCancelAppointment } from '@/features/portal/api'
import type { AppointmentDetail } from '@/features/portal/schema'

export function CancelBookingDialog({
  appointment,
  open,
  onOpenChange,
}: {
  appointment: AppointmentDetail
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [error, setError] = useState<string | null>(null)
  const cancel = useCancelAppointment()

  const refundable = appointment.refund_amount != null

  const message = refundable
    ? appointment.refund_amount
      ? `A refund of ${formatMoney(
          appointment.refund_amount,
          appointment.service.currency ?? 'INR'
        )} will be processed to your original payment method.`
      : 'No payment was taken, so there is nothing to refund.'
    : (appointment.cancellation_policy ??
      "If you're eligible under the cancellation policy, refunds are processed within 5–7 business days.")

  const handleConfirm = async () => {
    setError(null)
    try {
      await cancel.mutateAsync(appointment.id)
      onOpenChange(false)
      toast.success('Booking cancelled.')
    } catch (err) {
      setError(toApiError(err).message)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Cancel this booking?</DialogTitle>
          <DialogDescription>
            The slot will be released and made available to others.
          </DialogDescription>
        </DialogHeader>

        <Alert variant="destructive">
          <AlertTitle className="text-destructive">
            Before you cancel
          </AlertTitle>
          <AlertDescription>{message}</AlertDescription>
        </Alert>

        {error ? (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Keep booking
          </Button>
          <Button
            variant="destructive"
            disabled={cancel.isPending}
            onClick={() => void handleConfirm()}
          >
            {cancel.isPending ? 'Cancelling…' : 'Cancel booking'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
