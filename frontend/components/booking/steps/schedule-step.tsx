'use client'

import { AlertTriangleIcon } from 'lucide-react'

import { SlotPicker } from '@/components/booking/slot-picker'
import { Button } from '@/components/ui/button'

import { displayDate, displaySlotTime, type DateKey } from '@/lib/utils/dates'

import type { Service } from '@/features/services/schema'

interface ScheduleStepProps {
  service: Service
  date: DateKey | null
  startAt: string | null
  slotTakenError: string | null
  onSelectDateTime: (date: DateKey, startAt: string, slotLabel: string) => void
  onContinue: () => void
  onBack: () => void
}

export function ScheduleStep({
  service,
  date,
  startAt,
  slotTakenError,
  onSelectDateTime,
  onContinue,
  onBack,
}: ScheduleStepProps) {
  const canContinue = Boolean(date && startAt)

  return (
    <div className="flex flex-col gap-4">
      {slotTakenError && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive"
        >
          <AlertTriangleIcon className="mt-0.5 size-4 shrink-0" />
          <span>
            {slotTakenError} Here are the closest options — pick a new time.
          </span>
        </div>
      )}

      <div className="flex flex-col gap-1">
        <h2 className="font-serif text-2xl tracking-tight">{service.name}</h2>
        {date && startAt && (
          <p className="text-sm text-muted-foreground">
            {displayDate(date)} at {displaySlotTime(startAt)}
          </p>
        )}
      </div>

      <SlotPicker
        serviceId={service.id}
        date={date}
        startAt={startAt}
        onSelect={onSelectDateTime}
      />

      <div className="flex justify-between">
        <Button variant="ghost" onClick={onBack}>
          Back
        </Button>
        <Button size="lg" disabled={!canContinue} onClick={onContinue}>
          Continue
        </Button>
      </div>
    </div>
  )
}
