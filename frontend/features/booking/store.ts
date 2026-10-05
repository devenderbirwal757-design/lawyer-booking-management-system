'use client'

import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

import type {
  Appointment,
  BookingDetails,
  PaymentOrder,
} from '@/features/booking/schema'

export interface BookingDraft {
  step: number
  serviceId: string | null
  serviceSlug: string | null
  date: string | null
  startAt: string | null
  slotLabel: string | null
  details: BookingDetails
  appointment: Appointment | null
  paymentOrder: PaymentOrder | null
  idempotencyKey: string
}

interface BookingStore extends BookingDraft {
  setStep: (step: number) => void
  setService: (serviceId: string, slug: string) => void
  setDateTime: (date: string, startAt: string, slotLabel: string) => void
  setDetails: (details: BookingDetails) => void
  setAppointment: (appointment: Appointment) => void
  setPaymentOrder: (order: PaymentOrder) => void
  reset: () => void
}

const initialDraft: BookingDraft = {
  step: 0,
  serviceId: null,
  serviceSlug: null,
  date: null,
  startAt: null,
  slotLabel: null,
  details: { name: '', phone: '', email: '', notes: '' },
  appointment: null,
  paymentOrder: null,
  idempotencyKey: '',
}

export const useBookingStore = create<BookingStore>()(
  persist<BookingStore, [], [], Partial<BookingDraft>>(
    (set) => ({
      ...initialDraft,

      setStep: (step) => set((state) => ({ ...state, step })),

      setService: (serviceId, serviceSlug) =>
        set((state) => ({
          ...state,
          serviceId,
          serviceSlug,
          date: initialDraft.date,
          startAt: initialDraft.startAt,
          slotLabel: initialDraft.slotLabel,
          appointment: initialDraft.appointment,
          paymentOrder: initialDraft.paymentOrder,
        })),

      setDateTime: (date, startAt, slotLabel) =>
        set((state) => ({
          ...state,
          date,
          startAt,
          slotLabel,
          appointment: null,
          paymentOrder: null,
        })),

      setDetails: (details) => set((state) => ({ ...state, details })),

      setAppointment: (appointment) =>
        set((state) => ({ ...state, appointment })),

      setPaymentOrder: (paymentOrder) =>
        set((state) => ({ ...state, paymentOrder })),

      reset: () =>
        set({ ...initialDraft, idempotencyKey: crypto.randomUUID() }),
    }),
    {
      name: 'booking-draft',
      storage: createJSONStorage(() => window.sessionStorage),
      partialize: (state) => ({
        step: state.step,
        serviceId: state.serviceId,
        serviceSlug: state.serviceSlug,
        date: state.date,
        startAt: state.startAt,
        slotLabel: state.slotLabel,
        details: state.details,
        appointment: state.appointment,
        paymentOrder: state.paymentOrder,
        idempotencyKey: state.idempotencyKey,
      }),
    }
  )
)
