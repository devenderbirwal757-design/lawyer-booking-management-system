export const endpoints = {
  services: {
    list: (params?: { status?: string }) => {
      const query = params
        ? `?${new URLSearchParams(params as Record<string, string>)}`
        : ''
      return `/services${query}`
    },
    detail: (slug: string) => `/services/${slug}`,
  },
  providers: {
    detail: (id: string) => `/providers/${id}`,
  },
  availability: {
    slots: (params: { service_id: string; date: string }) =>
      `/availability/slots?${new URLSearchParams(params)}`,
    dates: (params: { service_id: string; month: string }) =>
      `/availability/dates?${new URLSearchParams(params)}`,
  },
  auth: {
    adminLogin: '/auth/admin/login',
    adminLogout: '/auth/admin/logout',
    customerLogout: '/auth/logout',
    refresh: '/auth/refresh',
    otpRequest: '/auth/otp/request',
    otpVerify: '/auth/otp/verify',
    me: '/auth/me',
  },
  appointments: {
    create: '/appointments',
    detail: (id: string) => `/appointments/${id}`,
  },
  payments: {
    createOrder: '/payments/create-order',
    webhook: '/payments/webhook',
    receipt: (id: string) => `/payments/${id}/receipt`,
  },
  me: {
    appointments: (params?: { status?: string }) => {
      const query = params
        ? `?${new URLSearchParams(params as Record<string, string>)}`
        : ''
      return `/me/appointments${query}`
    },
    appointment: (id: string) => `/me/appointments/${id}`,
    cancel: (id: string) => `/me/appointments/${id}/cancel`,
    reschedule: (id: string) => `/me/appointments/${id}/reschedule`,
    payments: '/me/payments',
    profile: '/me/profile',
  },
  admin: {
    dashboard: '/admin/reports/dashboard',
    services: '/admin/services',
    service: (id: string) => `/admin/services/${id}`,
    availabilityRules: '/admin/availability/rules',
    availabilityRule: (id: string) => `/admin/availability/rules/${id}`,
    availabilityExceptions: '/admin/availability/exceptions',
    availabilityException: (id: string) =>
      `/admin/availability/exceptions/${id}`,
    calendar: (params: Record<string, string>) =>
      `/admin/calendar?${new URLSearchParams(params)}`,
    appointments: (params: Record<string, string>) =>
      `/admin/appointments?${new URLSearchParams(params)}`,
    appointment: (id: string) => `/admin/appointments/${id}`,
    appointmentAction: (id: string, action: string) =>
      `/admin/appointments/${id}/${action}`,
    customers: (params?: { q?: string }) => {
      const query = params
        ? `?${new URLSearchParams(params as Record<string, string>)}`
        : ''
      return `/admin/customers${query}`
    },
    customer: (id: string) => `/admin/customers/${id}`,
    customerNotes: (id: string) => `/admin/customers/${id}/notes`,
    payments: (params?: Record<string, string>) =>
      `/admin/payments${params ? `?${new URLSearchParams(params)}` : ''}`,
    payment: (id: string) => `/admin/payments/${id}`,
    refund: (id: string) => `/admin/payments/${id}/refund`,
    refunds: (params?: { status?: string }) => {
      const query = params
        ? `?${new URLSearchParams(params as Record<string, string>)}`
        : ''
      return `/admin/refunds${query}`
    },
    refundSettle: (id: string) => `/admin/refunds/${id}/settle`,
    reportsAppointments: (params: Record<string, string>) =>
      `/admin/reports/appointments?${new URLSearchParams(params)}`,
    reportsRevenue: (params: Record<string, string>) =>
      `/admin/reports/revenue?${new URLSearchParams(params)}`,
    auditLogs: (params?: Record<string, string>) =>
      `/admin/audit-logs${params ? `?${new URLSearchParams(params)}` : ''}`,
    settings: '/admin/settings',
  },
} as const
