'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api/client'
import { endpoints } from '@/lib/api/endpoints'
import { queryKeys } from '@/lib/api/query-keys'

import {
  adminAppointmentSchema,
  adminPaymentSchema,
  adminRefundsResponseSchema,
  adminServicesResponseSchema,
  adminSettingsSchema,
  appointmentReportSchema,
  availabilityExceptionsResponseSchema,
  availabilityRulesResponseSchema,
  revenueReportSchema,
  adminAppointmentsResponseSchema,
  adminAppointmentDetailSchema,
  adminCalendarResponseSchema,
  adminCustomerDetailSchema,
  adminCustomersResponseSchema,
  adminDashboardSchema,
  adminPaymentsResponseSchema,
  auditLogsResponseSchema,
  type AdminAppointmentsResponse,
  type AdminCalendarEntry,
  type AdminRefund,
  type AdminRefundsResponse,
  type AdminService,
  type AdminSettings,
  type AppointmentReport,
  type AvailabilityException,
  type AvailabilityRule,
  type RevenueReport,
  type AdminCustomersResponse,
  type AdminPaymentsResponse,
  type AuditLogsResponse,
  type AdminDashboard,
} from '@/features/admin/schema'
import type { AppointmentStatus } from '@/features/booking/schema'

export interface AdminAppointmentsFilters {
  date?: string
  status?: string
  service_id?: string
  payment_status?: string
  customer_id?: string
  q?: string
  page?: number
  page_size?: number
}

export function useAdminDashboard() {
  return useQuery({
    queryKey: queryKeys.admin.reports.dashboard(),
    queryFn: async (): Promise<AdminDashboard> => {
      const payload = await api.get<unknown>(endpoints.admin.dashboard)
      const parsed = adminDashboardSchema.safeParse(payload)
      return parsed.success
        ? parsed.data
        : {
            today_count: 0,
            upcoming_count: 0,
            customer_count: 0,
            revenue_today: 0,
            revenue_month: 0,
            currency: 'INR',
          }
    },
    staleTime: 15_000,
  })
}

export function useAdminAppointments(filters: AdminAppointmentsFilters = {}) {
  const queryParams = Object.entries(filters).reduce<Record<string, string>>(
    (acc, [key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        acc[key] = String(value)
      }
      return acc
    },
    {}
  )

  return useQuery({
    queryKey: [queryKeys.admin.appointments.all, { filters: queryParams }],
    queryFn: async (): Promise<AdminAppointmentsResponse> => {
      const payload = await api.get<unknown>(
        endpoints.admin.appointments(queryParams)
      )
      const parsed = adminAppointmentsResponseSchema.safeParse(payload)
      return parsed.success
        ? parsed.data
        : { count: 0, next: null, previous: null, results: [] }
    },
    staleTime: 15_000,
  })
}

export function useAdminAppointment(id: string) {
  return useQuery({
    queryKey: queryKeys.admin.appointments.detail(id),
    queryFn: () =>
      api
        .get<unknown>(endpoints.admin.appointment(id))
        .then((payload) => adminAppointmentSchema.parse(payload)),
    enabled: Boolean(id),
    staleTime: 15_000,
  })
}

export function useAdminAppointmentDetail(id: string) {
  return useQuery({
    queryKey: queryKeys.admin.appointments.detail(id),
    queryFn: () =>
      api
        .get<unknown>(endpoints.admin.appointment(id))
        .then((payload) => adminAppointmentDetailSchema.parse(payload)),
    enabled: Boolean(id),
    staleTime: 15_000,
  })
}

type AdminAction = 'confirm' | 'cancel' | 'complete' | 'no-show'

const ACTION_STATUS: Partial<Record<AdminAction, AppointmentStatus>> = {
  confirm: 'CONFIRMED',
  cancel: 'CANCELLED',
  complete: 'COMPLETED',
  'no-show': 'NO_SHOW',
}

export function useAdminAppointmentAction() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      action,
      body,
    }: {
      id: string
      action: AdminAction
      body?: unknown
    }) => api.post<void>(endpoints.admin.appointmentAction(id, action), body),
    onMutate: async ({ id, action }) => {
      await queryClient.cancelQueries({
        queryKey: queryKeys.admin.appointments.all,
      })
      const previous = queryClient.getQueriesData<AdminAppointmentsResponse>({
        queryKey: queryKeys.admin.appointments.all,
      })
      const nextStatus = ACTION_STATUS[action]
      if (nextStatus) {
        queryClient.setQueriesData<AdminAppointmentsResponse>(
          { queryKey: queryKeys.admin.appointments.all },
          (old) =>
            old
              ? {
                  ...old,
                  results: old.results.map((row) =>
                    row.id === id ? { ...row, status: nextStatus } : row
                  ),
                }
              : old
        )
      }
      return { previous }
    },
    onError: (_error, _vars, context) => {
      context?.previous.forEach(([key, value]) => {
        queryClient.setQueryData(key, value)
      })
    },
    onSettled: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.admin.appointments.all,
      })
    },
  })
}

export function useAdminRescheduleAppointment() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, startAt }: { id: string; startAt: string }) =>
      api.post<void>(endpoints.admin.appointmentAction(id, 'reschedule'), {
        start_at: startAt,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.admin.appointments.all,
      })
    },
  })
}

export function useAdminCalendar(view: string, from: string, to: string) {
  return useQuery({
    queryKey: queryKeys.admin.calendar({ view, from, to }),
    queryFn: async (): Promise<AdminCalendarEntry[]> => {
      const payload = await api.get<unknown>(
        endpoints.admin.calendar({
          view,
          from,
          to,
        })
      )
      const parsed = adminCalendarResponseSchema.safeParse(payload)
      if (!parsed.success) {
        return []
      }
      return Array.isArray(parsed.data) ? parsed.data : parsed.data.entries
    },
    enabled: Boolean(view && from && to),
    staleTime: 15_000,
  })
}

export function useBlockCalendarTime() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { date: string; start_at: string; end_at: string }) =>
      api.post<void>(endpoints.admin.availabilityExceptions, { ...body }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['admin', 'calendar'] })
    },
  })
}

export function useAdminCustomers(filters: { q?: string; page?: number } = {}) {
  return useQuery({
    queryKey: [...queryKeys.admin.customers.list(), { filters }],
    queryFn: async (): Promise<AdminCustomersResponse> => {
      const payload = await api.get<unknown>(endpoints.admin.customers(filters))
      const parsed = adminCustomersResponseSchema.safeParse(payload)
      return parsed.success
        ? parsed.data
        : { count: 0, next: null, previous: null, results: [] }
    },
    staleTime: 15_000,
  })
}

export function useAdminCustomer(id: string) {
  return useQuery({
    queryKey: queryKeys.admin.customers.detail(id),
    queryFn: () =>
      api
        .get<unknown>(endpoints.admin.customer(id))
        .then((payload) => adminCustomerDetailSchema.parse(payload)),
    enabled: Boolean(id),
    staleTime: 15_000,
  })
}

export function useUpdateClientNotes() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, notes }: { id: string; notes: string }) =>
      api.patch<void>(endpoints.admin.customerNotes(id), { notes }),
    onSuccess: (_data, { id }) => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.admin.customers.detail(id),
      })
    },
  })
}

function cleanParams(
  filters: Record<string, string | number | undefined>
): Record<string, string> {
  return Object.fromEntries(
    Object.entries(filters)
      .filter(([, value]) => value !== undefined && value !== '')
      .map(([key, value]) => [key, String(value)])
  )
}

export function useAdminPayments(
  filters: Record<string, string | undefined> = {}
): ReturnType<typeof useQuery<AdminPaymentsResponse>> {
  const params = cleanParams(filters)
  return useQuery({
    queryKey: [...queryKeys.admin.payments.all, { filters: params }],
    queryFn: async (): Promise<AdminPaymentsResponse> => {
      const payload = await api.get<unknown>(endpoints.admin.payments(params))
      const parsed = adminPaymentsResponseSchema.safeParse(payload)
      return parsed.success
        ? parsed.data
        : { count: 0, next: null, previous: null, results: [] }
    },
    staleTime: 15_000,
  })
}

export function useAdminAuditLogs(
  filters: Record<string, string | undefined> = {}
): ReturnType<typeof useQuery<AuditLogsResponse>> {
  const params = cleanParams(filters)
  return useQuery({
    queryKey: [...queryKeys.admin.auditLogs.all, { filters: params }],
    queryFn: async (): Promise<AuditLogsResponse> => {
      const payload = await api.get<unknown>(endpoints.admin.auditLogs(params))
      const parsed = auditLogsResponseSchema.safeParse(payload)
      return parsed.success
        ? parsed.data
        : { count: 0, next: null, previous: null, results: [] }
    },
    staleTime: 15_000,
  })
}

function toArray<T>(value: unknown): T[] {
  if (Array.isArray(value)) {
    return value as T[]
  }
  if (value && typeof value === 'object') {
    const results = (value as { results?: unknown }).results
    if (Array.isArray(results)) {
      return results as T[]
    }
  }
  return []
}

export function useAdminServices() {
  return useQuery({
    queryKey: queryKeys.admin.services.all,
    queryFn: async (): Promise<AdminService[]> => {
      const payload = await api.get<unknown>(endpoints.admin.services)
      const parsed = adminServicesResponseSchema.safeParse(payload)
      return parsed.success ? toArray<AdminService>(parsed.data) : []
    },
    staleTime: 15_000,
  })
}

function useInvalidateServices() {
  const queryClient = useQueryClient()
  return async () => {
    await queryClient.invalidateQueries({
      queryKey: queryKeys.admin.services.all,
    })
  }
}

export function useCreateService() {
  const invalidate = useInvalidateServices()
  return useMutation({
    mutationFn: (body: AdminServiceInput) =>
      api.post<AdminService>(endpoints.admin.services, body),
    onSuccess: invalidate,
  })
}

export function useUpdateService() {
  const invalidate = useInvalidateServices()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: AdminServiceInput }) =>
      api.patch<AdminService>(endpoints.admin.service(id), body),
    onSuccess: invalidate,
  })
}

export function useDeleteService() {
  const invalidate = useInvalidateServices()
  return useMutation({
    mutationFn: (id: string) => api.del<void>(endpoints.admin.service(id)),
    onSuccess: invalidate,
  })
}

export interface AdminServiceInput {
  name: string
  description?: string
  duration_minutes: number
  price: number
  is_active: boolean
}

export function useAvailabilityRules() {
  return useQuery({
    queryKey: ['admin', 'availability', 'rules'],
    queryFn: async (): Promise<AvailabilityRule[]> => {
      const payload = await api.get<unknown>(endpoints.admin.availabilityRules)
      const parsed = availabilityRulesResponseSchema.safeParse(payload)
      return parsed.success ? toArray<AvailabilityRule>(parsed.data) : []
    },
    staleTime: 15_000,
  })
}

function useInvalidateAvailability() {
  const queryClient = useQueryClient()
  return async () => {
    await queryClient.invalidateQueries({ queryKey: ['admin', 'availability'] })
  }
}

export function useCreateAvailabilityRule() {
  const invalidate = useInvalidateAvailability()
  return useMutation({
    mutationFn: (body: {
      weekday: number
      start_time: string
      end_time: string
    }) => api.post<AvailabilityRule>(endpoints.admin.availabilityRules, body),
    onSuccess: invalidate,
  })
}

export function useDeleteAvailabilityRule() {
  const invalidate = useInvalidateAvailability()
  return useMutation({
    mutationFn: (id: string) =>
      api.del<void>(endpoints.admin.availabilityRule(id)),
    onSuccess: invalidate,
  })
}

export function useAvailabilityExceptions() {
  return useQuery({
    queryKey: ['admin', 'availability', 'exceptions'],
    queryFn: async (): Promise<AvailabilityException[]> => {
      const payload = await api.get<unknown>(
        endpoints.admin.availabilityExceptions
      )
      const parsed = availabilityExceptionsResponseSchema.safeParse(payload)
      return parsed.success ? toArray<AvailabilityException>(parsed.data) : []
    },
    staleTime: 15_000,
  })
}

export function useCreateAvailabilityException() {
  const invalidate = useInvalidateAvailability()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: {
      date: string
      start_time?: string
      end_time?: string
      note?: string
    }) =>
      api.post<AvailabilityException>(
        endpoints.admin.availabilityExceptions,
        body
      ),
    onSuccess: () => {
      void invalidate()
      void queryClient.invalidateQueries({ queryKey: ['admin', 'calendar'] })
    },
  })
}

export function useDeleteAvailabilityException() {
  const invalidate = useInvalidateAvailability()
  return useMutation({
    mutationFn: (id: string) =>
      api.del<void>(endpoints.admin.availabilityException(id)),
    onSuccess: invalidate,
  })
}

export function useAdminPayment(id: string) {
  return useQuery({
    queryKey: queryKeys.admin.payments.detail(id),
    queryFn: () =>
      api
        .get<unknown>(endpoints.admin.payment(id))
        .then((payload) => adminPaymentSchema.parse(payload)),
    enabled: Boolean(id),
    staleTime: 15_000,
  })
}

export function useRefundPayment() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      amount,
      reason,
    }: {
      id: string
      amount: number
      reason: string
    }) => api.post<AdminRefund>(endpoints.admin.refund(id), { amount, reason }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.admin.payments.all,
      })
      void queryClient.invalidateQueries({
        queryKey: queryKeys.admin.refunds.all,
      })
    },
  })
}

export function useAdminRefunds(filters: { status?: string } = {}) {
  return useQuery({
    queryKey: [...queryKeys.admin.refunds.all, { filters }],
    queryFn: async (): Promise<AdminRefundsResponse> => {
      const payload = await api.get<unknown>(endpoints.admin.refunds(filters))
      const parsed = adminRefundsResponseSchema.safeParse(payload)
      return parsed.success
        ? parsed.data
        : { count: 0, next: null, previous: null, results: [] }
    },
    staleTime: 15_000,
  })
}

export function useSettleRefund() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      api.post<void>(endpoints.admin.refundSettle(id), {}),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.admin.refunds.all,
      })
      void queryClient.invalidateQueries({
        queryKey: queryKeys.admin.payments.all,
      })
    },
  })
}

export function useAppointmentReport(params: { from: string; to: string }) {
  return useQuery({
    queryKey: queryKeys.admin.reports.appointments(params),
    queryFn: async (): Promise<AppointmentReport> => {
      const payload = await api.get<unknown>(
        endpoints.admin.reportsAppointments({
          ...params,
          group_by: 'status',
        })
      )
      const parsed = appointmentReportSchema.safeParse(payload)
      return parsed.success ? parsed.data : { count: 0, by_status: {} }
    },
    enabled: Boolean(params.from && params.to),
    staleTime: 30_000,
  })
}

export function useRevenueReport(params: { from: string; to: string }) {
  return useQuery({
    queryKey: queryKeys.admin.reports.revenue(params),
    queryFn: async (): Promise<RevenueReport> => {
      const payload = await api.get<unknown>(
        endpoints.admin.reportsRevenue(params)
      )
      const parsed = revenueReportSchema.safeParse(payload)
      return parsed.success
        ? parsed.data
        : { total: 0, currency: 'INR', series: [] }
    },
    enabled: Boolean(params.from && params.to),
    staleTime: 30_000,
  })
}

export function useAdminSettings() {
  return useQuery({
    queryKey: queryKeys.admin.settings,
    queryFn: async (): Promise<AdminSettings> => {
      const payload = await api.get<unknown>(endpoints.admin.settings)
      const parsed = adminSettingsSchema.safeParse(payload)
      return parsed.success
        ? parsed.data
        : {
            business_name: '',
            timezone: 'Asia/Kolkata',
            currency: 'INR',
            faq: [],
            reminder_offsets: [],
            working_hours: [],
          }
    },
    staleTime: 30_000,
  })
}

export function useUpdateAdminSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: Partial<AdminSettings>) =>
      api.patch<AdminSettings>(endpoints.admin.settings, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.settings })
      void queryClient.invalidateQueries({
        queryKey: queryKeys.admin.dashboard,
      })
    },
  })
}
