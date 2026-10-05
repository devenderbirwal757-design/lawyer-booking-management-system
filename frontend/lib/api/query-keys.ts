export const queryKeys = {
  services: {
    all: ['services'] as const,
    list: (status?: string) => [...queryKeys.services.all, { status }] as const,
    detail: (slug: string) => [...queryKeys.services.all, slug] as const,
  },
  providers: {
    detail: (id: string) => ['providers', id] as const,
  },
  availability: {
    dates: (serviceId: string, month: string) =>
      ['availability', 'dates', serviceId, month] as const,
    slots: (serviceId: string, date: string) =>
      ['availability', 'slots', serviceId, date] as const,
  },
  auth: {
    me: ['auth', 'me'] as const,
  },
  appointments: {
    detail: (id: string) => ['appointments', id] as const,
  },
  payments: {
    receipt: (id: string) => ['payments', 'receipt', id] as const,
  },
  me: {
    appointments: {
      all: ['me', 'appointments'] as const,
      list: (status?: string) =>
        [...queryKeys.me.appointments.all, { status }] as const,
      detail: (id: string) => ['me', 'appointments', id] as const,
    },
    payments: {
      all: ['me', 'payments'] as const,
      list: () => [...queryKeys.me.payments.all] as const,
    },
    profile: ['me', 'profile'] as const,
  },
  admin: {
    dashboard: ['admin', 'dashboard'] as const,
    services: {
      all: ['admin', 'services'] as const,
      list: (filters?: Record<string, unknown>) =>
        [...queryKeys.admin.services.all, { filters }] as const,
      detail: (id: string) => [...queryKeys.admin.services.all, id] as const,
    },
    appointments: {
      all: ['admin', 'appointments'] as const,
      list: (filters?: Record<string, unknown>) =>
        [...queryKeys.admin.appointments.all, { filters }] as const,
      detail: (id: string) =>
        [...queryKeys.admin.appointments.all, id] as const,
    },
    calendar: (params: Record<string, unknown>) =>
      ['admin', 'calendar', params] as const,
    customers: {
      all: ['admin', 'customers'] as const,
      list: (filters?: Record<string, unknown>) =>
        [...queryKeys.admin.customers.all, { filters }] as const,
      detail: (id: string) => [...queryKeys.admin.customers.all, id] as const,
    },
    payments: {
      all: ['admin', 'payments'] as const,
      list: (filters?: Record<string, unknown>) =>
        [...queryKeys.admin.payments.all, { filters }] as const,
      detail: (id: string) => [...queryKeys.admin.payments.all, id] as const,
    },
    refunds: {
      all: ['admin', 'refunds'] as const,
      list: (status?: string) =>
        [...queryKeys.admin.refunds.all, { status }] as const,
    },
    reports: {
      all: ['admin', 'reports'] as const,
      dashboard: () => [...queryKeys.admin.reports.all, 'dashboard'] as const,
      appointments: (params: Record<string, unknown>) =>
        [...queryKeys.admin.reports.all, 'appointments', params] as const,
      revenue: (params: Record<string, unknown>) =>
        [...queryKeys.admin.reports.all, 'revenue', params] as const,
    },
    auditLogs: {
      all: ['admin', 'audit-logs'] as const,
      list: (filters?: Record<string, unknown>) =>
        [...queryKeys.admin.auditLogs.all, { filters }] as const,
    },
    settings: ['admin', 'settings'] as const,
  },
} as const
