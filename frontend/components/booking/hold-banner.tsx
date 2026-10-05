'use client'

import { TimerIcon } from 'lucide-react'

import { useCountdownTo } from '@/lib/hooks/use-countdown'

export function HoldBanner({
  expiresAt,
  onExpired,
}: {
  expiresAt: string | null
  onExpired?: () => void
}) {
  const { secondsLeft, isRunning } = useCountdownTo(expiresAt, onExpired)

  if (!expiresAt || !isRunning) {
    return null
  }

  const minutes = Math.floor(secondsLeft / 60)
  const seconds = secondsLeft % 60

  return (
    <div
      role="status"
      className="flex items-center justify-center gap-2 rounded-xl border border-amber-600/40 bg-amber-500/10 px-4 py-3 text-sm font-medium text-amber-700"
    >
      <TimerIcon className="size-4" />
      Your slot is reserved. Complete payment within {minutes}:
      {seconds.toString().padStart(2, '0')}
    </div>
  )
}
