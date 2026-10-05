'use client'

import { SearchIcon } from 'lucide-react'
import { useEffect, useState } from 'react'

import { useUrlFilters } from '@/lib/hooks/use-url-filters'
import { useDebounce } from '@/lib/hooks/use-debounce'

import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

import { APPOINTMENT_STATUS_LABELS } from '@/components/shared/status-badge'
import { PAYMENT_STATUS_LABELS } from '@/components/shared/status-badge'

function Filter({
  placeholder,
  value,
  onValueChange,
  options,
}: {
  placeholder: string
  value: string
  onValueChange: (value: string) => void
  options: { value: string; label: string }[]
}) {
  return (
    <Select value={value} onValueChange={onValueChange}>
      <SelectTrigger className="h-8 w-40 text-sm" aria-label={placeholder}>
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="__all__">{placeholder}</SelectItem>
        {options.map((option) => (
          <SelectItem key={option.value} value={option.value}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

export function AppointmentFilterBar({
  defaults,
  onSearch,
}: {
  defaults: { date?: string; status?: string; payment_status?: string }
  onSearch?: (q: string) => void
}) {
  const { values, set } = useUrlFilters({
    date: defaults.date ?? new Date().toISOString().slice(0, 10),
    status: defaults.status ?? '',
    payment_status: defaults.payment_status ?? '',
    q: '',
  })

  const [search, setSearch] = useState(values.q)
  const debounced = useDebounce(search)

  useEffect(() => {
    if (onSearch) {
      onSearch(debounced)
    } else {
      set('q', debounced)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced])

  const toParam = (value: string) => (value === '__all__' ? '' : value)

  return (
    <div className="flex flex-wrap items-center gap-2">
      <label className="flex items-center gap-2 text-sm text-muted-foreground">
        <span className="sr-only">Filter by date</span>
        <Input
          type="date"
          value={values.date}
          onChange={(e) => set('date', e.target.value)}
          className="h-8 w-fit"
        />
      </label>

      <Filter
        placeholder="All statuses"
        value={values.status || '__all__'}
        onValueChange={(value) => set('status', toParam(value))}
        options={Object.entries(APPOINTMENT_STATUS_LABELS).map(
          ([value, label]) => ({ value, label })
        )}
      />

      <Filter
        placeholder="All payments"
        value={values.payment_status || '__all__'}
        onValueChange={(value) => set('payment_status', toParam(value))}
        options={Object.entries(PAYMENT_STATUS_LABELS).map(
          ([value, label]) => ({ value, label })
        )}
      />

      <div className="relative ml-auto">
        <SearchIcon className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search client…"
          className="h-8 w-56 pl-8 text-sm"
          aria-label="Search appointments"
        />
      </div>
    </div>
  )
}
