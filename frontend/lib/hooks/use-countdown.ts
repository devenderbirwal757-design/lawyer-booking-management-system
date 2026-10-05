'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

import { secondsUntil } from '@/lib/utils/date-time'

interface UseCountdownOptions {
  autoStart?: boolean
  onComplete?: () => void
}

export function useCountdown(
  totalSeconds: number,
  options: UseCountdownOptions = {}
) {
  const { autoStart = false, onComplete } = options
  const [secondsLeft, setSecondsLeft] = useState(autoStart ? totalSeconds : 0)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const onCompleteRef = useRef(onComplete)

  useEffect(() => {
    onCompleteRef.current = onComplete
  }, [onComplete])

  const stop = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
  }, [])

  useEffect(() => stop, [stop])

  const start = useCallback(() => {
    stop()
    setSecondsLeft(totalSeconds)
    intervalRef.current = setInterval(() => {
      setSecondsLeft((prev) => {
        if (prev <= 1) {
          stop()
          onCompleteRef.current?.()
          return 0
        }
        return prev - 1
      })
    }, 1000)
  }, [stop, totalSeconds])

  useEffect(() => {
    if (autoStart) {
      start()
    }
  }, [autoStart, start])

  return {
    secondsLeft,
    isRunning: secondsLeft > 0,
    start,
    stop,
  }
}

export function formatCountdown(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

export function useCountdownTo(
  deadline: string | null,
  onComplete?: () => void
) {
  const [secondsLeft, setSecondsLeft] = useState(() =>
    deadline ? secondsUntil(deadline) : 0
  )
  const onCompleteRef = useRef(onComplete)

  useEffect(() => {
    onCompleteRef.current = onComplete
  }, [onComplete])

  useEffect(() => {
    if (!deadline) {
      setSecondsLeft(0)
      return
    }

    const tick = () => {
      const next = secondsUntil(deadline)
      setSecondsLeft(next)
      if (next === 0) {
        clearInterval(interval)
        onCompleteRef.current?.()
      }
    }

    tick()
    const interval = setInterval(tick, 1000)
    return () => clearInterval(interval)
  }, [deadline])

  return { secondsLeft, isRunning: secondsLeft > 0 }
}
