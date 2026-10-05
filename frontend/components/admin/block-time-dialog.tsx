'use client'

import { toast } from 'sonner'

import { useBlockCalendarTime } from '@/features/admin/api'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

import { displayDate, numericDate, todayKey } from '@/lib/utils/dates'

export function BlockTimeDialog({
  date,
  startAt,
  open,
  onOpenChange,
}: {
  date: string
  startAt: string
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const block = useBlockCalendarTime()

  const handleConfirm = () => {
    block.mutate(
      {
        date: numericDate(date) ?? date,
        start_at: startAt,
        end_at: startAt,
      },
      {
        onSuccess: () => {
          onOpenChange(false)
          toast.success('Time blocked.')
        },
        onError: () => toast.error('Could not block this time.'),
      }
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Block this time</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          {displayDate(date ?? todayKey())} at{' '}
          <span className="font-medium text-foreground">{startAt}</span> will be
          marked as unavailable for new bookings.
        </p>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="secondary"
            disabled={block.isPending}
            onClick={handleConfirm}
          >
            {block.isPending ? 'Blocking…' : 'Block time'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
