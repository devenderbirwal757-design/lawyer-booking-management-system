'use client'

import { CalendarDaysIcon } from 'lucide-react'
import { useRouter, useSearchParams } from 'next/navigation'

import { Input } from '@/components/ui/input'

export function DateFilter({
  paramName = 'date',
  defaultValue,
}: {
  paramName?: string
  defaultValue: string
}) {
  const router = useRouter()
  const searchParams = useSearchParams()
  const value = searchParams.get(paramName) ?? defaultValue

  const apply = (next: string) => {
    const params = new URLSearchParams(searchParams.toString())
    if (next && next !== defaultValue) {
      params.set(paramName, next)
    } else {
      params.delete(paramName)
    }
    const query = params.toString()
    router.replace(query ? `?${query}` : window.location.pathname)
  }

  return (
    <label className="flex items-center gap-2 text-sm text-muted-foreground">
      <CalendarDaysIcon className="size-4" />
      <span className="sr-only">Filter by date</span>
      <Input
        type="date"
        value={value}
        onChange={(e) => apply(e.target.value)}
        className="h-8 w-fit"
      />
    </label>
  )
}
