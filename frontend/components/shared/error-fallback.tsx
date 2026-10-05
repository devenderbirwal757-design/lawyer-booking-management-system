'use client'

import { AlertTriangleIcon, RefreshCwIcon } from 'lucide-react'
import Link from 'next/link'

import { toApiError } from '@/lib/api/error'

import { Button } from '@/components/ui/button'

export function ErrorFallback({
  error,
  reset,
  scope = 'this page',
  showHome = true,
}: {
  error: unknown
  reset?: () => void
  scope?: string
  showHome?: boolean
}) {
  const isNetwork =
    !(error instanceof Error) ||
    error.name === 'TypeError' ||
    /fetch|network|Failed to fetch/i.test(
      error instanceof Error ? error.message : String(error)
    )

  const message = isNetwork
    ? 'We could not reach the server. Check your connection and try again.'
    : toApiError(error).message

  return (
    <div className="mx-auto flex w-full max-w-md flex-col items-center gap-4 py-16 text-center">
      <span
        aria-hidden
        className="flex size-12 items-center justify-center rounded-full bg-destructive/10 text-destructive"
      >
        <AlertTriangleIcon className="size-6" />
      </span>
      <div className="flex flex-col gap-1.5">
        <h1 className="font-serif text-xl font-semibold">
          Something went wrong
        </h1>
        <p className="text-sm text-muted-foreground">
          {isNetwork
            ? `We could not load ${scope}. Your data is safe — nothing was changed.`
            : message}
        </p>
      </div>
      <div className="flex flex-wrap items-center justify-center gap-2">
        {reset ? (
          <Button onClick={reset}>
            <RefreshCwIcon className="size-4" /> Try again
          </Button>
        ) : null}
        {showHome ? (
          <Button variant="outline" asChild>
            <Link href="/">Go to homepage</Link>
          </Button>
        ) : null}
      </div>
    </div>
  )
}
