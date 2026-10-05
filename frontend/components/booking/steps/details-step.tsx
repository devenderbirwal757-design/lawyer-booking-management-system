'use client'

import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'

import { OtpVerify } from '@/components/booking/otp-verify'
import { Button } from '@/components/ui/button'
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldError,
  FieldLabel,
} from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'

import {
  bookingDetailsSchema,
  type BookingDetails,
} from '@/features/booking/schema'

interface DetailsStepProps {
  initialDetails: BookingDetails
  onSubmit: (details: BookingDetails) => void
  onBack: () => void
}

const resolver = zodResolver(bookingDetailsSchema)

export function DetailsStep({
  initialDetails,
  onSubmit,
  onBack,
}: DetailsStepProps) {
  const [submitted, setSubmitted] = useState<BookingDetails | null>(null)

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<BookingDetails>({
    resolver,
    defaultValues: initialDetails,
  })

  const continueToVerify = handleSubmit((details) => {
    setSubmitted(details)
  })

  if (submitted && submitted.phone) {
    return (
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <h2 className="font-serif text-2xl tracking-tight">
            Verify your number
          </h2>
          <p className="text-sm text-muted-foreground">
            Bookings need a verified mobile number so we can send your
            confirmation.
          </p>
        </div>

        <OtpVerify
          phone={submitted.phone}
          name={submitted.name}
          email={submitted.email || undefined}
          onVerified={() => onSubmit(submitted)}
        />

        <div className="flex justify-start">
          <Button
            variant="ghost"
            onClick={() => {
              setSubmitted(null)
            }}
          >
            Edit details
          </Button>
        </div>
      </div>
    )
  }

  return (
    <form
      onSubmit={continueToVerify}
      noValidate
      className="flex flex-col gap-5"
    >
      <div className="flex flex-col gap-1">
        <h2 className="font-serif text-2xl tracking-tight">Your details</h2>
        <p className="text-sm text-muted-foreground">
          Used to confirm the booking and send reminders.
        </p>
      </div>

      <Field>
        <FieldLabel htmlFor="name">Full name</FieldLabel>
        <FieldContent>
          <Input
            id="name"
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
        <FieldLabel htmlFor="phone">Mobile number</FieldLabel>
        <FieldContent>
          <Input
            id="phone"
            type="tel"
            inputMode="tel"
            autoComplete="tel"
            maxLength={10}
            placeholder="10-digit mobile"
            {...register('phone')}
          />
          <FieldError
            errors={errors.phone ? [{ message: errors.phone.message }] : []}
          />
        </FieldContent>
      </Field>

      <Field>
        <FieldLabel htmlFor="email">
          Email{' '}
          <span className="font-normal text-muted-foreground">(optional)</span>
        </FieldLabel>
        <FieldContent>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            placeholder="name@example.com"
            {...register('email')}
          />
          <FieldDescription>
            Optional — so we can email your confirmation and reminder. If you
            skip it, view everything in the client portal instead.
          </FieldDescription>
          <FieldError
            errors={errors.email ? [{ message: errors.email.message }] : []}
          />
        </FieldContent>
      </Field>

      <Field>
        <FieldLabel htmlFor="notes">Notes for the advocate</FieldLabel>
        <FieldContent>
          <Textarea
            id="notes"
            rows={3}
            maxLength={500}
            placeholder="Anything we should know? (optional)"
            {...register('notes')}
          />
          <FieldError
            errors={errors.notes ? [{ message: errors.notes.message }] : []}
          />
        </FieldContent>
      </Field>

      <div className="flex justify-between">
        <Button type="button" variant="ghost" onClick={onBack}>
          Back
        </Button>
        <Button type="submit" size="lg">
          Send verification code
        </Button>
      </div>
    </form>
  )
}
