'use client'

import { MoreHorizontalIcon } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { useAdminAppointmentAction } from '@/features/admin/api'
import type { AdminAppointment } from '@/features/admin/schema'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Textarea } from '@/components/ui/textarea'

import { ConfirmDialog } from '@/components/shared/confirm-dialog'

import { AdminRescheduleDialog } from '@/components/admin/admin-reschedule-dialog'

type PendingAction = 'confirm' | 'complete' | 'no-show' | null

export function AppointmentActions({
  appointment,
}: {
  appointment: AdminAppointment
}) {
  const [pending, setPending] = useState<PendingAction>(null)
  const [reasonOpen, setReasonOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [rescheduleOpen, setRescheduleOpen] = useState(false)

  const action = useAdminAppointmentAction()
  const { status } = appointment

  const canConfirm = status === 'PENDING_PAYMENT'
  const canManage = status === 'CONFIRMED'
  const canCancel = status === 'PENDING_PAYMENT' || status === 'CONFIRMED'
  const canReschedule = canCancel

  const runAction = (next: NonNullable<PendingAction>) => {
    setPending(null)
    action.mutate(
      { id: appointment.id, action: next },
      {
        onSuccess: () => toast.success('Appointment updated'),
        onError: () => toast.error('Could not update appointment'),
      }
    )
  }

  const confirmAction = () => {
    if (pending) {
      runAction(pending)
    }
  }

  const cancel = () => {
    setReasonOpen(false)
    action.mutate(
      { id: appointment.id, action: 'cancel', body: { reason } },
      {
        onSuccess: () => {
          setReason('')
          toast.success('Appointment cancelled')
        },
        onError: () => toast.error('Could not cancel appointment'),
      }
    )
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="outline"
            size="icon-sm"
            aria-label="Appointment actions"
          >
            <MoreHorizontalIcon className="size-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuLabel>Actions</DropdownMenuLabel>
          {canConfirm ? (
            <>
              <DropdownMenuItem onClick={() => setPending('confirm')}>
                Confirm
              </DropdownMenuItem>
            </>
          ) : null}
          {canManage ? (
            <>
              <DropdownMenuItem onClick={() => setPending('complete')}>
                Mark completed
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => setPending('no-show')}>
                Mark no-show
              </DropdownMenuItem>
            </>
          ) : null}
          {canCancel ? (
            <>
              <DropdownMenuItem onSelect={() => setReasonOpen(true)}>
                Cancel…
              </DropdownMenuItem>
            </>
          ) : null}
          {canReschedule ? (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => setRescheduleOpen(true)}>
                Reschedule…
              </DropdownMenuItem>
            </>
          ) : null}
        </DropdownMenuContent>
      </DropdownMenu>

      <ConfirmDialog
        open={pending !== null}
        onOpenChange={(open) => {
          if (!open) setPending(null)
        }}
        title={`${PENDING_ACTION_LABELS[pending ?? 'confirm']} appointment`}
        description={`This will update the appointment status to ${PENDING_ACTION_STATUS[pending ?? 'confirm']}.`}
        confirmLabel="Save"
        destructive={pending === 'no-show'}
        loading={action.isPending}
        onConfirm={confirmAction}
      />

      <Dialog open={reasonOpen} onOpenChange={setReasonOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Cancel appointment</DialogTitle>
            <DialogDescription>
              The client will be refunded per the cancellation policy.
            </DialogDescription>
          </DialogHeader>
          <Textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Reason for cancellation (required)"
            className="min-h-24"
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setReasonOpen(false)}>
              Keep appointment
            </Button>
            <Button
              variant="destructive"
              disabled={!reason.trim() || action.isPending}
              onClick={cancel}
            >
              {action.isPending ? 'Please wait…' : 'Cancel appointment'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AdminRescheduleDialog
        open={rescheduleOpen}
        onOpenChange={setRescheduleOpen}
        appointment={appointment}
      />
    </>
  )
}

const PENDING_ACTION_LABELS: Record<string, string> = {
  confirm: 'Confirm',
  complete: 'Complete',
  'no-show': 'Mark no-show',
}

const PENDING_ACTION_STATUS: Record<string, string> = {
  confirm: 'CONFIRMED',
  complete: 'COMPLETED',
  'no-show': 'NO_SHOW',
}
