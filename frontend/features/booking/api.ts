'use client'

import { useQuery } from '@tanstack/react-query'

import { api } from '@/lib/api/client'
import { endpoints } from '@/lib/api/endpoints'
import { queryKeys } from '@/lib/api/query-keys'

import {
  appointmentSchema,
  availabilityDatesSchema,
  availabilitySlotsSchema,
  paymentOrderSchema,
  type Appointment,
  type AvailabilityDates,
  type CreateAppointmentPayload,
  type CreateOrderPayload,
  type PaymentOrder,
  type RawAvailabilitySlot,
} from '@/features/booking/schema'

export function useAvailabilityDates(serviceId: string, month: string) {
  return useQuery({
    queryKey: queryKeys.availability.dates(serviceId, month),
    queryFn: () =>
      api.get<AvailabilityDates>(
        endpoints.availability.dates({ service_id: serviceId, month }),
        { schema: availabilityDatesSchema }
      ),
    enabled: Boolean(serviceId && month),
    staleTime: 60_000,
  })
}

export function useAvailabilitySlots(serviceId: string, date: string) {
  return useQuery({
    queryKey: queryKeys.availability.slots(serviceId, date),
    queryFn: async (): Promise<string[]> => {
      const payload = await api.get<unknown>(
        endpoints.availability.slots({ service_id: serviceId, date })
      )
      const parsed = availabilitySlotsSchema.safeParse(payload)
      if (!parsed.success) {
        return []
      }
      const raw = Array.isArray(parsed.data) ? parsed.data : parsed.data.slots
      return normalizeSlots(raw)
    },
    enabled: Boolean(serviceId && date),
    staleTime: 15_000,
    refetchOnWindowFocus: true,
  })
}

function normalizeSlots(raw: RawAvailabilitySlot[]): string[] {
  return raw.map((slot) => (typeof slot === 'string' ? slot : slot.start_at))
}

export async function createAppointment(
  payload: CreateAppointmentPayload,
  idempotencyKey: string
): Promise<Appointment> {
  const data = await api.post<unknown>(endpoints.appointments.create, payload, {
    idempotencyKey,
  })
  const parsed = appointmentSchema.parse(data)
  return parsed
}

export async function createPaymentOrder(
  payload: CreateOrderPayload
): Promise<PaymentOrder> {
  const data = await api.post<unknown>(endpoints.payments.createOrder, payload)
  return paymentOrderSchema.parse(data)
}

export async function cancelAppointment(id: string): Promise<void> {
  return api.post<void>(endpoints.me.cancel(id))
}

export function useAppointment(id: string) {
  return useQuery({
    queryKey: queryKeys.appointments.detail(id),
    queryFn: () => fetchAppointment(id),
    enabled: Boolean(id),
  })
}

export async function fetchAppointment(id: string): Promise<Appointment> {
  const data = await api.get<unknown>(endpoints.appointments.detail(id))
  return appointmentSchema.parse(data)
}

export async function pollAppointmentUntilConfirmed(
  id: string,
  attempts = 5
): Promise<Appointment> {
  let last: Appointment
  for (let i = 0; i < attempts; i += 1) {
    last = await fetchAppointment(id)
    if (last.status === 'CONFIRMED') {
      return last
    }
    await new Promise((resolve) => setTimeout(resolve, 1000))
  }
  return last!
}
