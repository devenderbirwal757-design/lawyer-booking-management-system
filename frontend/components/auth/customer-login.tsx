'use client'

import { zodResolver } from '@hookform/resolvers/zod'
import { useSearchParams } from 'next/navigation'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'

import { Button } from '@/components/ui/button'
import {
  Field,
  FieldContent,
  FieldError,
  FieldLabel,
} from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { OtpInput } from '@/components/shared/otp-input'
import { ApiError, ErrorCodes } from '@/lib/api/error'
import { formatCountdown, useCountdown } from '@/lib/hooks/use-countdown'
import { indianPhoneSchema } from '@/lib/utils/phone'

import { requestOtp, verifyOtp } from '@/features/auth/api'

const RESEND_SECONDS = 300

type PhoneForm = { phone: string }

function safeNextPath(searchParams: URLSearchParams): string {
  const next = searchParams.get('next') ?? '/'
  return next.startsWith('/') && !next.startsWith('//') ? next : '/'
}

function authErrorMessage(error: unknown): string | null {
  if (!(error instanceof ApiError)) {
    return 'Something went wrong. Please try again.'
  }
  if (error.code === ErrorCodes.rateLimited) {
    return 'Too many attempts. Please wait a few minutes and try again.'
  }
  return error.message
}

export function CustomerLogin() {
  const searchParams = useSearchParams()

  const [phone, setPhone] = useState('')
  const [otp, setOtp] = useState('')
  const [step, setStep] = useState<'phone' | 'otp'>('phone')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const {
    secondsLeft,
    isRunning: resendLocked,
    start: startCountdown,
  } = useCountdown(RESEND_SECONDS)

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<PhoneForm>({
    resolver: zodResolver(z.object({ phone: indianPhoneSchema })),
  })

  const submitPhone = handleSubmit(async ({ phone: submitted }) => {
    setError(null)
    setSubmitting(true)
    try {
      await requestOtp(submitted)
      setPhone(submitted)
      setStep('otp')
      startCountdown()
    } catch (err) {
      setError(authErrorMessage(err))
    } finally {
      setSubmitting(false)
    }
  })

  const submitOtp = async (code: string) => {
    setError(null)
    setSubmitting(true)
    try {
      await verifyOtp({ phone, code })
      const target = safeNextPath(searchParams)
      window.location.assign(target)
    } catch (err) {
      setOtp('')
      setError(authErrorMessage(err))
      toast.error("That code didn't work. Please check and try again.")
    } finally {
      setSubmitting(false)
    }
  }

  const resend = async () => {
    setError(null)
    setSubmitting(true)
    try {
      await requestOtp(phone)
      startCountdown()
      setOtp('')
      toast.success('A new code has been sent.')
    } catch (err) {
      setError(authErrorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="mx-auto w-full max-w-sm px-4 py-16">
      <div className="flex flex-col gap-2 text-center">
        <h1 className="font-serif text-3xl tracking-tight">Customer login</h1>
        <p className="text-sm text-muted-foreground">
          Log in with your mobile number. No password needed.
        </p>
      </div>

      {error && (
        <p
          role="alert"
          className="mt-6 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive"
        >
          {error}
        </p>
      )}

      {step === 'phone' ? (
        <form
          onSubmit={submitPhone}
          className="mt-8 flex flex-col gap-5"
          noValidate
        >
          <Field>
            <FieldLabel htmlFor="phone">Mobile number</FieldLabel>
            <FieldContent>
              <Input
                id="phone"
                type="tel"
                inputMode="tel"
                autoComplete="tel"
                maxLength={10}
                placeholder="10-digit mobile number"
                disabled={submitting}
                {...register('phone')}
              />
              <FieldError
                errors={errors.phone ? [{ message: errors.phone.message }] : []}
              />
            </FieldContent>
          </Field>

          <Button type="submit" size="lg" disabled={submitting}>
            {submitting ? 'Sending code…' : 'Send one-time password'}
          </Button>
        </form>
      ) : (
        <div className="mt-8 flex flex-col gap-5">
          <div className="flex flex-col gap-2">
            <p className="text-sm text-muted-foreground">
              We sent a 6-digit code to{' '}
              <span className="font-medium text-foreground">+91 {phone}</span>
            </p>
            <OtpInput
              value={otp}
              onValueChange={setOtp}
              onComplete={submitOtp}
              disabled={submitting}
            />
            <p className="text-center text-xs text-muted-foreground">
              Code expires in {formatCountdown(secondsLeft)}
            </p>
          </div>

          <div className="flex items-center justify-between text-sm">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={submitting}
              onClick={() => {
                setStep('phone')
                setError(null)
              }}
            >
              Change number
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={resendLocked || submitting}
              onClick={resend}
            >
              {resendLocked
                ? `Resend in ${formatCountdown(secondsLeft)}`
                : 'Resend code'}
            </Button>
          </div>

          <Button
            type="button"
            size="lg"
            disabled={otp.length !== 6 || submitting}
            onClick={() => submitOtp(otp)}
          >
            {submitting ? 'Logging in…' : 'Verify & log in'}
          </Button>
        </div>
      )}

      <p className="mt-10 text-center text-xs leading-relaxed text-muted-foreground">
        By continuing you agree to our{' '}
        <a href="/terms" className="underline underline-offset-4">
          Terms of Service
        </a>
        . Your number is only used to authenticate bookings.
      </p>
    </div>
  )
}
