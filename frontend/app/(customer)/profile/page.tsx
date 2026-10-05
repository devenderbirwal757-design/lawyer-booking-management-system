'use client'

import { zodResolver } from '@hookform/resolvers/zod'
import { QueryError } from '@/components/shared/query-error'
import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'

import { OtpInput } from '@/components/shared/otp-input'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldError,
  FieldLabel,
} from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { toApiError } from '@/lib/api/error'
import { formatCountdown, useCountdown } from '@/lib/hooks/use-countdown'

import { requestOtp, verifyOtp } from '@/features/auth/api'
import {
  updateProfileSchema,
  type UpdateProfile,
} from '@/features/portal/schema'
import { useMeProfile, useUpdateMeProfile } from '@/features/portal/api'

const PHONE_PATTERN = /^[6-9]\d{9}$/
const RESEND_SECONDS = 300

export default function ProfilePage() {
  const profile = useMeProfile()
  const update = useUpdateMeProfile()

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="font-serif text-2xl font-semibold tracking-tight">
          Profile
        </h1>
        <p className="text-sm text-muted-foreground">
          Your name, contact details, and preferences.
        </p>
      </div>

      {profile.isLoading ? (
        <div className="grid gap-6 sm:grid-cols-2">
          <Skeleton className="h-64 rounded-2xl" />
          <Skeleton className="h-64 rounded-2xl" />
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          <ProfileForm
            name={profile.data?.name ?? ''}
            email={profile.data?.email ?? ''}
            onSave={async (values) => {
              try {
                await update.mutateAsync({
                  name: values.name,
                  email: values.email || null,
                })
                toast.success('Profile updated.')
              } catch (err) {
                toast.error(toApiError(err).message)
              }
            }}
          />
          <PhoneChangeCard
            currentPhone={profile.data?.phone ?? ''}
            onPhoneChanged={async (phone) => {
              try {
                await update.mutateAsync({ phone })
                toast.success('Mobile number updated.')
              } catch (err) {
                toast.error(toApiError(err).message)
              }
            }}
          />
        </div>
      )}
    </div>
  )
}

function ProfileForm({
  name,
  email,
  onSave,
}: {
  name: string
  email: string
  onSave: (values: UpdateProfile) => Promise<void>
}) {
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<UpdateProfile>({
    resolver: zodResolver(updateProfileSchema),
    defaultValues: { name, email: email ?? '' },
  })

  useEffect(() => {
    reset({ name, email: email ?? '' })
  }, [name, email, reset])

  return (
    <Card>
      <CardHeader>
        <CardTitle>Your details</CardTitle>
        <CardDescription>
          Used on receipts and when we need to reach you.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form
          onSubmit={handleSubmit((values) => onSave(values))}
          noValidate
          className="flex flex-col gap-4"
        >
          <Field>
            <FieldLabel htmlFor="profile-name">Full name</FieldLabel>
            <FieldContent>
              <Input
                id="profile-name"
                autoComplete="name"
                placeholder="Your name"
                {...register('name')}
              />
              <FieldError
                errors={errors.name ? [{ message: errors.name.message }] : []}
              />
            </FieldContent>
          </Field>

          <Field>
            <FieldLabel htmlFor="profile-email">
              Email{' '}
              <span className="font-normal text-muted-foreground">
                (optional)
              </span>
            </FieldLabel>
            <FieldContent>
              <Input
                id="profile-email"
                type="email"
                autoComplete="email"
                placeholder="name@example.com"
                {...register('email')}
              />
              <FieldDescription>
                Optional — used for email confirmations and reminders.
              </FieldDescription>
              <FieldError
                errors={errors.email ? [{ message: errors.email.message }] : []}
              />
            </FieldContent>
          </Field>

          <Button type="submit" disabled={isSubmitting} className="w-fit">
            {isSubmitting ? 'Saving…' : 'Save changes'}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}

function PhoneChangeCard({
  currentPhone,
  onPhoneChanged,
}: {
  currentPhone: string
  onPhoneChanged: (phone: string) => Promise<void>
}) {
  const [phone, setPhone] = useState('')
  const [otp, setOtp] = useState('')
  const [phase, setPhase] = useState<'enter' | 'otp'>('enter')
  const [error, setError] = useState<string | null>(null)
  const [sending, setSending] = useState(false)

  const {
    secondsLeft,
    isRunning,
    start: startCountdown,
  } = useCountdown(RESEND_SECONDS)

  const sendCode = async () => {
    setError(null)
    if (!PHONE_PATTERN.test(phone)) {
      setError('Enter a valid 10-digit mobile number')
      return
    }
    setSending(true)
    try {
      await requestOtp(phone)
      setOtp('')
      startCountdown()
      setPhase('otp')
    } catch (err) {
      setError(toApiError(err).message)
    } finally {
      setSending(false)
    }
  }

  if (phase === 'otp') {
    return (
      <PhoneCard currentPhone={currentPhone}>
        <div className="flex flex-col gap-4">
          <p className="text-sm text-muted-foreground">
            Enter the code sent to +91 {phone}.
          </p>
          <OtpInput
            value={otp}
            onValueChange={setOtp}
            onComplete={async (code) => {
              setError(null)
              try {
                await verifyOtp({ phone, code })
                await onPhoneChanged(phone)
                setPhase('enter')
                setPhone('')
                setOtp('')
                toast.success('Mobile number verified and updated.')
              } catch (err) {
                setError(toApiError(err).message)
              }
            }}
          />
          <div className="flex items-center justify-between text-sm">
            <button
              type="button"
              disabled={isRunning}
              onClick={() => void sendCode()}
              className="text-primary disabled:pointer-events-none disabled:opacity-50"
            >
              {isRunning
                ? `Resend in ${formatCountdown(secondsLeft)}`
                : 'Resend code'}
            </button>
            <button
              type="button"
              onClick={() => setPhase('enter')}
              className="text-muted-foreground hover:text-foreground"
            >
              Use a different number
            </button>
          </div>
          {error ? <QueryError error={new Error(error)} /> : null}
        </div>
      </PhoneCard>
    )
  }

  return (
    <PhoneCard currentPhone={currentPhone}>
      <div className="flex flex-col gap-4">
        <Field>
          <FieldLabel htmlFor="new-phone">New mobile number</FieldLabel>
          <FieldContent>
            <div className="flex gap-2">
              <Input
                id="new-phone"
                type="tel"
                inputMode="tel"
                autoComplete="tel"
                maxLength={10}
                placeholder="10-digit mobile"
                value={phone}
                onChange={(e) =>
                  setPhone(e.target.value.replace(/\D/g, '').slice(0, 10))
                }
              />
              <Button
                type="button"
                variant="outline"
                disabled={sending}
                onClick={() => void sendCode()}
              >
                {sending ? 'Sending…' : 'Send code'}
              </Button>
            </div>
            <FieldDescription>
              We&apos;ll send a one-time code to verify the new number.
            </FieldDescription>
            <FieldError errors={error ? [{ message: error }] : []} />
          </FieldContent>
        </Field>
      </div>
    </PhoneCard>
  )
}

function PhoneCard({
  children,
  currentPhone,
}: {
  children: React.ReactNode
  currentPhone: string
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Mobile number</CardTitle>
        <CardDescription>
          Current number:{' '}
          <span className="font-medium text-foreground">
            +91 {currentPhone}
          </span>
        </CardDescription>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  )
}
