'use client'

import { useRouter, useSearchParams } from 'next/navigation'

import { useUrlFilters } from '@/lib/hooks/use-url-filters'

import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

import { addDaysKey, todayKey } from '@/lib/utils/dates'

const PRESETS = [
  { value: 'today', label: 'Today' },
  { value: 'week', label: 'Last 7 days' },
  { value: 'month', label: 'Last 30 days' },
  { value: 'custom', label: 'Custom' },
] as const

export function RangeSelector() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { values, set } = useUrlFilters({
    range: 'week',
    from: '',
    to: '',
  })

  const applyPreset = (preset: string) => {
    const params = new URLSearchParams(searchParams.toString())
    const today = todayKey()
    if (preset === 'today') {
      params.set('from', today)
      params.set('to', today)
    } else if (preset === 'week') {
      params.set('from', addDaysKey(today, -6))
      params.set('to', today)
    } else if (preset === 'month') {
      params.set('from', addDaysKey(today, -29))
      params.set('to', today)
    } else {
      params.delete('from')
      params.delete('to')
    }
    params.set('range', preset)
    const query = params.toString()
    router.replace(query ? `?${query}` : window.location.pathname)
  }

  const activePreset = values.range

  return (
    <div className="flex flex-wrap items-end gap-3">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="range-preset">Range</Label>
        <Select value={activePreset} onValueChange={applyPreset}>
          <SelectTrigger id="range-preset" className="h-9 w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PRESETS.map((preset) => (
              <SelectItem key={preset.value} value={preset.value}>
                {preset.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {activePreset === 'custom' ? (
        <>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="range-from">From</Label>
            <Input
              id="range-from"
              type="date"
              value={values.from}
              onChange={(e) => set('from', e.target.value)}
              className="h-9 w-40"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="range-to">To</Label>
            <Input
              id="range-to"
              type="date"
              value={values.to}
              onChange={(e) => set('to', e.target.value)}
              className="h-9 w-40"
            />
          </div>
        </>
      ) : null}

      {values.from && values.to ? (
        <p className="pb-2 text-sm text-muted-foreground">
          {values.from} → {values.to}
        </p>
      ) : null}
    </div>
  )
}
