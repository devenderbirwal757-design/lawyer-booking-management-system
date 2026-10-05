'use client'

import { useRouter, useSearchParams } from 'next/navigation'
import { useCallback } from 'react'

export function useUrlFilters(defaults: Record<string, string>) {
  const router = useRouter()
  const searchParams = useSearchParams()

  const values = Object.fromEntries(
    Object.entries(defaults).map(([key, fallback]) => [
      key,
      searchParams.get(key) ?? fallback,
    ])
  )

  const set = useCallback(
    (key: string, value: string) => {
      const params = new URLSearchParams(searchParams.toString())
      const next = value && value !== defaults[key] ? value : ''
      if (next) {
        params.set(key, next)
      } else {
        params.delete(key)
      }
      const query = params.toString()
      router.replace(query ? `?${query}` : window.location.pathname)
    },
    [defaults, router, searchParams]
  )

  const clear = useCallback(() => {
    router.replace(window.location.pathname)
  }, [router])

  return { values, set, clear }
}
