'use client'

import { useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'next/navigation'
import { useEffect, useMemo, useState } from 'react'

import { Stepper } from '@/components/booking/stepper'
import { ConfirmationStep } from '@/components/booking/steps/confirmation-step'
import { DetailsStep } from '@/components/booking/steps/details-step'
import { PaymentStep } from '@/components/booking/steps/payment-step'
import { ScheduleStep } from '@/components/booking/steps/schedule-step'
import { ServiceStep } from '@/components/booking/steps/service-step'
import { queryKeys } from '@/lib/api/query-keys'

import { useActiveServices } from '@/features/services/api'
import type { Service } from '@/features/services/schema'
import { useBookingStore } from '@/features/booking/store'

export function BookingWizard({
  initialServices,
}: {
  initialServices?: Service[]
}) {
  const searchParams = useSearchParams()
  const queryClient = useQueryClient()

  const services = useActiveServices(
    initialServices ? { results: initialServices } : undefined
  )

  const {
    step,
    serviceId,
    date,
    startAt,
    slotLabel,
    details,
    appointment,
    paymentOrder,
    idempotencyKey,
    setStep,
    setService,
    setDateTime,
    setDetails,
    setAppointment,
    setPaymentOrder,
    reset,
  } = useBookingStore()

  const [slotTakenError, setSlotTakenError] = useState<string | null>(null)

  useEffect(() => {
    if (!idempotencyKey) {
      useBookingStore.getState().reset()
    }
  }, [idempotencyKey])

  const slugParam = searchParams.get('service')

  const selectedService = useMemo(() => {
    const servicesList = services.data?.results ?? []
    if (serviceId) {
      return servicesList.find((service) => service.id === serviceId) ?? null
    }
    if (slugParam) {
      return servicesList.find((service) => service.slug === slugParam) ?? null
    }
    return null
  }, [services.data, serviceId, slugParam])

  useEffect(() => {
    if (serviceId || !slugParam || !services.data) {
      return
    }
    const match = services.data.results.find(
      (service) => service.slug === slugParam
    )
    if (match) {
      setService(match.id, match.slug)
    }
  }, [serviceId, slugParam, services.data, setService])

  const invalidateSlots = () => {
    if (serviceId && date) {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.availability.slots(serviceId, date),
      })
    }
  }

  const handleSlotTaken = () => {
    setSlotTakenError('That time was just taken while you were booking.')
    invalidateSlots()
    setStep(1)
  }

  const handleHoldExpired = () => {
    setSlotTakenError('Your reservation expired and the slot was released.')
    invalidateSlots()
    setStep(1)
  }

  const handleHeldCancelled = () => {
    invalidateSlots()
    setStep(1)
  }

  const handleConfirmed = (confirmed: typeof appointment) => {
    if (!confirmed) {
      return
    }
    setAppointment(confirmed)
    void queryClient.removeQueries({
      queryKey: queryKeys.appointments.detail(confirmed.id),
    })
    setStep(4)
  }

  const resetBooking = () => {
    reset()
    setSlotTakenError(null)
    setStep(0)
  }

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-10">
      <Stepper
        current={step}
        onNavigate={(index) => index < step && setStep(index)}
      />

      <div className="rounded-2xl border border-border bg-background p-5 sm:p-8">
        {step === 0 && (
          <ServiceStep
            selectedService={selectedService}
            onSelect={(service) => setService(service.id, service.slug)}
            onContinue={() => setStep(1)}
          />
        )}

        {step === 1 && selectedService && (
          <ScheduleStep
            service={selectedService}
            date={date}
            startAt={startAt}
            slotTakenError={slotTakenError}
            onSelectDateTime={(nextDate, nextStartAt, nextSlotLabel) => {
              setSlotTakenError(null)
              setDateTime(nextDate, nextStartAt, nextSlotLabel)
            }}
            onContinue={() => setStep(2)}
            onBack={() => setStep(0)}
          />
        )}

        {step === 2 && selectedService && (
          <DetailsStep
            initialDetails={details}
            onSubmit={(nextDetails) => {
              setDetails(nextDetails)
              setStep(3)
            }}
            onBack={() => setStep(1)}
          />
        )}

        {step === 3 && selectedService && date && startAt && (
          <PaymentStep
            service={selectedService}
            details={details}
            date={date}
            startAt={slotLabel ?? startAt}
            idempotencyKey={idempotencyKey}
            appointment={appointment}
            paymentOrder={paymentOrder}
            onAppointmentCreated={setAppointment}
            onOrderCreated={setPaymentOrder}
            onConfirmed={handleConfirmed}
            onSlotTaken={handleSlotTaken}
            onHoldExpired={handleHoldExpired}
            onHeldCancelled={handleHeldCancelled}
            onBack={() => setStep(1)}
          />
        )}

        {step === 4 && appointment && (
          <ConfirmationStep appointment={appointment} />
        )}

        {step === 4 && !appointment && (
          <div className="flex flex-col items-center gap-3 py-8 text-center">
            <p className="text-sm text-muted-foreground">
              This booking session has ended.
            </p>
            <button
              onClick={resetBooking}
              className="text-sm text-primary underline underline-offset-4"
            >
              Start a new booking
            </button>
          </div>
        )}
      </div>

      {step > 1 && (
        <p className="text-center text-xs text-muted-foreground">
          Your draft is saved on this device. You can leave and come back to
          finish booking.
        </p>
      )}
    </div>
  )
}
