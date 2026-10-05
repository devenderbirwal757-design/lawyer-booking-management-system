'use client'

import { useCallback, useRef } from 'react'

import { cn } from 'cn'

import { Input } from '@/components/ui/input'

const OTP_LENGTH = 6

interface OtpInputProps {
  value: string
  onValueChange: (value: string) => void
  onComplete?: (value: string) => void
  disabled?: boolean
  autoFocus?: boolean
}

export function OtpInput({
  value,
  onValueChange,
  onComplete,
  disabled,
  autoFocus = true,
}: OtpInputProps) {
  const inputsRef = useRef<Array<HTMLInputElement | null>>([])

  const setDigit = useCallback(
    (index: number, digit: string) => {
      const next = value.split('')
      next[index] = digit
      const joined = next.join('').slice(0, OTP_LENGTH)
      onValueChange(joined)
      if (digit && index < OTP_LENGTH - 1) {
        inputsRef.current[index + 1]?.focus()
      } else if (joined.length === OTP_LENGTH) {
        onComplete?.(joined)
      }
    },
    [onComplete, onValueChange, value]
  )

  const handleKeyDown = (
    index: number,
    e: React.KeyboardEvent<HTMLInputElement>
  ) => {
    if (e.key === 'Backspace') {
      e.preventDefault()
      if (value[index]) {
        setDigit(index, '')
      } else if (index > 0) {
        inputsRef.current[index - 1]?.focus()
        const next = value.split('')
        next[index - 1] = ''
        onValueChange(next.slice(0, OTP_LENGTH).join(''))
      }
      return
    }
    if (e.key === 'ArrowLeft' && index > 0) {
      inputsRef.current[index - 1]?.focus()
    }
    if (e.key === 'ArrowRight' && index < OTP_LENGTH - 1) {
      inputsRef.current[index + 1]?.focus()
    }
  }

  const handlePaste = (e: React.ClipboardEvent) => {
    e.preventDefault()
    const pasted = e.clipboardData.getData('text').replace(/\D/g, '')
    if (!pasted) {
      return
    }
    const digits = pasted.slice(0, OTP_LENGTH).split('')
    onValueChange(digits.join(''))
    inputsRef.current[Math.min(digits.length, OTP_LENGTH - 1)]?.focus()
    if (digits.length === OTP_LENGTH) {
      onComplete?.(digits.join(''))
    }
  }

  return (
    <div
      className="flex items-center justify-center gap-2"
      role="group"
      aria-label={`One-time password, ${OTP_LENGTH} digits`}
    >
      {Array.from({ length: OTP_LENGTH }).map((_, index) => (
        <Input
          key={index}
          ref={(el) => {
            inputsRef.current[index] = el
          }}
          type="text"
          inputMode="numeric"
          pattern="[0-9]*"
          maxLength={1}
          autoComplete={index === 0 ? 'one-time-code' : 'off'}
          autoFocus={autoFocus && index === 0}
          disabled={disabled}
          value={value[index] ?? ''}
          onChange={(e) => {
            const digit = e.target.value.replace(/\D/g, '')
            setDigit(index, digit)
          }}
          onKeyDown={(e) => handleKeyDown(index, e)}
          onPaste={handlePaste}
          aria-label={`Digit ${index + 1}`}
          className={cn(
            'h-12 w-10 text-center text-lg font-semibold tabular-nums',
            value[index] && 'border-primary'
          )}
        />
      ))}
    </div>
  )
}
