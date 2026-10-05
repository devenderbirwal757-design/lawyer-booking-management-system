'use client'

import { useState } from 'react'
import { toast } from 'sonner'

import { SlotPicker } from '@/components/booking/slot-picker'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { slotToIso, type DateKey } from '@/lib/utils/dates'

import { useAdminRescheduleAppointment } from '@/features/admin/api'
import type { AdminAppointment } from '@/features/admin/schema'

export function AdminRescheduleDialog({
  appointment,
  open,
  onOpenChange,
}: {
  appointment: AdminAppointment
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const reschedule = useAdminRescheduleAppointment()
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
      toast.success('Appointment rescheduled.')
    } catch {
      setError('Could not reschedule: the slot may no longer be available.')
    }
  }

  const canConfirm = Boolean(date && startAt)

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-h-[85dvh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Reschedule appointment</DialogTitle>
          <DialogDescription>
            Pick a new date and time. The client will be notified.
          </DialogDescription>
        </DialogHeader>

        {appointment.service?.id ? (
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
        ) : (
          <p className="text-sm text-muted-foreground">
            This appointment has no linked service, so it cannot be rescheduled
            yet.
          </p>
        )}

        {error ? <p className="text-sm text-destructive">{error}</p> : null}

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
