'use client'

import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { OtpInput } from '@/components/shared/otp-input'
import { ApiError, ErrorCodes } from '@/lib/api/error'
import { formatCountdown, useCountdown } from '@/lib/hooks/use-countdown'

import { requestOtp, verifyOtp } from '@/features/auth/api'

const RESEND_SECONDS = 300

function otpErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return 'Something went wrong. Please try again.'
  }
  if (error.code === ErrorCodes.rateLimited) {
    return 'Too many attempts. Please wait a few minutes and try again.'
  }
  if (error.status === 401) {
    return 'This code has expired. Request a new one.'
  }
  return error.message
}

interface OtpVerifyProps {
  phone: string
  name?: string
  email?: string
  onVerified: () => void
}

export function OtpVerify({ phone, name, email, onVerified }: OtpVerifyProps) {
  const [otp, setOtp] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [verifying, setVerifying] = useState(false)

  const {
    secondsLeft,
    isRunning: resendLocked,
    start: startCountdown,
  } = useCountdown(RESEND_SECONDS, { autoStart: true })

  const sendOtp = async () => {
    setError(null)
    try {
      await requestOtp(phone)
      startCountdown()
      setOtp('')
      toast.success('A verification code has been sent.')
    } catch (err) {
      setError(otpErrorMessage(err))
    }
  }

  useEffect(() => {
    void sendOtp()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const verify = async (code: string) => {
    setError(null)
    setVerifying(true)
    try {
      await verifyOtp({ phone, code, name, email })
      onVerified()
    } catch (err) {
      setOtp('')
      setError(otpErrorMessage(err))
    } finally {
      setVerifying(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <p className="text-sm text-muted-foreground">
          Verify +91 {phone} to confirm your booking.
        </p>
        <OtpInput
          value={otp}
          onValueChange={setOtp}
          onComplete={verify}
          disabled={verifying}
        />
        <p className="text-center text-xs text-muted-foreground">
          Code expires in {formatCountdown(secondsLeft)}
        </p>
      </div>

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}

      <div className="flex items-center justify-between text-sm">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={resendLocked || verifying}
          onClick={() => void sendOtp()}
        >
          {resendLocked
            ? `Resend in ${formatCountdown(secondsLeft)}`
            : 'Resend code'}
        </Button>
      </div>
    </div>
  )
}
