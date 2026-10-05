'use client'

import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { toast } from 'sonner'

import { SlotPicker } from '@/components/booking/slot-picker'
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
import { queryKeys } from '@/lib/api/query-keys'
import { toApiError } from '@/lib/api/error'
import { slotToIso, type DateKey } from '@/lib/utils/dates'

import { useRescheduleAppointment } from '@/features/portal/api'
import type { AppointmentDetail } from '@/features/portal/schema'

export function RescheduleDialog({
  appointment,
  open,
  onOpenChange,
}: {
  appointment: AppointmentDetail
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const queryClient = useQueryClient()
  const reschedule = useRescheduleAppointment()
  const [date, setDate] = useState<DateKey | null>(null)
  const [startAt, setStartAt] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleOpenChange = (next: boolean) => {
    if (next) {
      setDate(null)
      setStartAt(null)
      setError(null)
    }
    onOpenChange(next)
  }

  const handleConfirm = async () => {
    if (!date || !startAt) {
      return
    }
    setError(null)
    try {
      await reschedule.mutateAsync({
        id: appointment.id,
        startAt: slotToIso(date, startAt),
      })
      handleOpenChange(false)
      toast.success('Booking rescheduled.')
    } catch (err) {
      const apiError = toApiError(err)
      setError(apiError.message)
      if (apiError.isSlotUnavailable) {
        void queryClient.invalidateQueries({
          queryKey: queryKeys.availability.slots(appointment.service.id, date),
        })
      }
    }
  }

  const canConfirm = Boolean(date && startAt)

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-h-[85dvh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Reschedule your booking</DialogTitle>
          <DialogDescription>
            Pick a new date and time for this consultation.
          </DialogDescription>
        </DialogHeader>

        <SlotPicker
          serviceId={appointment.service.id}
          date={date}
          startAt={startAt}
          onSelect={(nextDate, nextStartAt, slotLabel) => {
            setError(null)
            setDate(nextDate)
            setStartAt(slotLabel || nextStartAt || null)
          }}
        />

        {error ? (
          <Alert variant="destructive">
            <AlertTitle className="text-destructive">
              Could not reschedule
            </AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}

        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)}>
            Close
          </Button>
          <Button
            disabled={!canConfirm || reschedule.isPending}
            onClick={() => void handleConfirm()}
          >
            {reschedule.isPending ? 'Rescheduling…' : 'Confirm new time'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
