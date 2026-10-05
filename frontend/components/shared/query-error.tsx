'use client'

import { RefreshCwIcon, WifiOffIcon } from 'lucide-react'

import { toApiError } from '@/lib/api/error'

import { Button } from '@/components/ui/button'

export function isNetworkError(error: unknown): boolean {
  if (!error) return false
  if (error instanceof TypeError) return true
  const message = error instanceof Error ? error.message : String(error)
  return /failed to fetch|networkerror|load failed|offline/i.test(message)
}

export function QueryError({
  error,
  onRetry,
  isRetrying,
  className,
}: {
  error: unknown
  onRetry?: () => void
  isRetrying?: boolean
  className?: string
}) {
  const offline = isNetworkError(error)
  const message = offline
    ? 'Could not reach the server. Check your connection and try again.'
    : toApiError(error).message

  return (
    <div
      role="alert"
      className={
        className ??
        'flex flex-wrap items-center gap-3 rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm'
      }
    >
      {offline ? (
        <WifiOffIcon className="size-4 shrink-0 text-destructive" aria-hidden />
      ) : null}
      <span className="flex-1 text-destructive">{message}</span>
      {onRetry ? (
        <Button
          variant="outline"
          size="sm"
          onClick={onRetry}
          disabled={isRetrying}
        >
          <RefreshCwIcon className="size-4" />
          {isRetrying ? 'Retrying…' : 'Retry'}
        </Button>
      ) : null}
    </div>
  )
}
