'use client'

import { useState } from 'react'
import { toast } from 'sonner'

import { useRefundPayment } from '@/features/admin/api'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'

export function RefundDialog({
  paymentId,
  amount: maxAmount,
  currency = 'INR',
  open,
  onOpenChange,
}: {
  paymentId: string
  amount: number
  currency?: string
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const refund = useRefundPayment()
  const [amount, setAmount] = useState('')
  const [reason, setReason] = useState('')

  const parsedAmount = Number(amount)
  const valid =
    Number.isFinite(parsedAmount) &&
    parsedAmount > 0 &&
    parsedAmount <= maxAmount &&
    reason.trim().length > 0

  const submit = () => {
    if (!valid) return
    refund.mutate(
      { id: paymentId, amount: parsedAmount, reason: reason.trim() },
      {
        onSuccess: () => {
          toast.success('Refund queued', {
            description: 'It stays pending until settled in the gateway.',
          })
          setAmount('')
          setReason('')
          onOpenChange(false)
        },
        onError: () => toast.error('Could not queue the refund'),
      }
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Refund payment</DialogTitle>
          <DialogDescription>
            Refunds are created as pending actions. Settle them once the gateway
            confirms.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="refund-amount">
              Amount ({currency}) — max {maxAmount}
            </Label>
            <Input
              id="refund-amount"
              type="number"
              min={1}
              max={maxAmount}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder={String(maxAmount)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="refund-reason">Reason</Label>
            <Textarea
              id="refund-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Why is this being refunded?"
              className="min-h-20"
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            disabled={!valid || refund.isPending}
            onClick={submit}
          >
            {refund.isPending ? 'Queuing…' : 'Queue refund'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
