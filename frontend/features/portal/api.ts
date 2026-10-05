'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api/client'
import { endpoints } from '@/lib/api/endpoints'
import { queryKeys } from '@/lib/api/query-keys'

import { cancelAppointment } from '@/features/booking/api'
import {
  appointmentDetailSchema,
  meAppointmentsResponseSchema,
  mePaymentsResponseSchema,
  type CustomerProfile,
  type MeAppointmentsResponse,
  type MePaymentsResponse,
  type ProfilePatch,
} from '@/features/portal/schema'

export type AppointmentListStatus = 'upcoming' | 'past' | 'cancelled'

export function useMeAppointments(status: AppointmentListStatus) {
  return useQuery({
    queryKey: queryKeys.me.appointments.list(status),
    queryFn: async (): Promise<MeAppointmentsResponse> => {
      const payload = await api.get<unknown>(
        endpoints.me.appointments({ status })
      )
      const parsed = meAppointmentsResponseSchema.safeParse(payload)
      return parsed.success
        ? parsed.data
        : { count: 0, next: null, previous: null, results: [] }
    },
    staleTime: 15_000,
  })
}

export function useMeAppointment(id: string) {
  return useQuery({
    queryKey: queryKeys.me.appointments.detail(id),
    queryFn: () =>
      api
        .get<unknown>(endpoints.me.appointment(id))
        .then((payload) => appointmentDetailSchema.parse(payload)),
    enabled: Boolean(id),
    staleTime: 15_000,
  })
}

export function useRescheduleAppointment() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, startAt }: { id: string; startAt: string }) =>
      api.post<void>(endpoints.me.reschedule(id), { start_at: startAt }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.me.appointments.all,
      })
    },
  })
}

export function useCancelAppointment() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => cancelAppointment(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.me.appointments.all,
      })
    },
  })
}

export function useMePayments() {
  return useQuery({
    queryKey: queryKeys.me.payments.list(),
    queryFn: async (): Promise<MePaymentsResponse> => {
      const payload = await api.get<unknown>(endpoints.me.payments)
      const parsed = mePaymentsResponseSchema.safeParse(payload)
      return parsed.success
        ? parsed.data
        : { count: 0, next: null, previous: null, results: [] }
    },
    staleTime: 15_000,
  })
}

export function useMeProfile() {
  return useQuery({
    queryKey: queryKeys.me.profile,
    queryFn: () => api.get<CustomerProfile>(endpoints.me.profile),
    staleTime: 30_000,
  })
}

export function useUpdateMeProfile() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (patch: ProfilePatch) =>
      api.patch<CustomerProfile>(endpoints.me.profile, patch),
    onSuccess: (updated) => {
      queryClient.setQueryData(queryKeys.me.profile, updated)
    },
  })
}
