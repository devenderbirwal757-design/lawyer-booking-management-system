import { z } from 'zod'

import {
  appointmentStatusSchema,
  paymentStatusSchema,
} from '@/features/booking/schema'
import {
  paymentSchema,
  statusHistoryEntrySchema,
} from '@/features/portal/schema'

export const adminDashboardSchema = z.object({
  today_count: z.number().catch(0),
  upcoming_count: z.number().catch(0),
  customer_count: z.number().catch(0),
  revenue_today: z.number().catch(0),
  revenue_month: z.number().catch(0),
  currency: z.string().optional().default('INR'),
})

export type AdminDashboard = z.infer<typeof adminDashboardSchema>

export const adminCustomerRefSchema = z.object({
  id: z.string().optional(),
  name: z.string().nullable().optional(),
  phone: z.string().optional(),
  email: z.string().nullable().optional(),
})

export const adminServiceRefSchema = z.object({
  id: z.string(),
  name: z.string().nullable().optional(),
  slug: z.string().optional(),
  duration_minutes: z.number().optional(),
  price: z.number().optional(),
})

export const adminPaymentRefSchema = z.object({
  id: z.string().optional(),
  order_id: z.string().optional(),
  amount: z.number().optional(),
  currency: z.string().optional(),
  status: paymentStatusSchema.optional(),
})

export const adminAppointmentSchema = z.object({
  id: z.string(),
  status: appointmentStatusSchema.optional(),
  start_at: z.string(),
  end_at: z.string().optional(),
  customer: adminCustomerRefSchema.optional(),
  service: adminServiceRefSchema.partial().optional(),
  payment: adminPaymentRefSchema.optional(),
  payment_order_id: z.string().optional(),
  created_at: z.string().optional(),
})

export type AdminAppointment = z.infer<typeof adminAppointmentSchema>

export const adminAppointmentsResponseSchema = z.object({
  count: z.number().optional().default(0),
  next: z.string().nullable().optional(),
  previous: z.string().nullable().optional(),
  results: z.array(adminAppointmentSchema),
})

export type AdminAppointmentsResponse = z.infer<
  typeof adminAppointmentsResponseSchema
>

export const adminAppointmentDetailSchema = adminAppointmentSchema.extend({
  status_history: z.array(statusHistoryEntrySchema).default([]),
  cancellation_policy: z.string().optional(),
  refund_amount: z.number().nullable().optional(),
})

export type AdminAppointmentDetail = z.infer<
  typeof adminAppointmentDetailSchema
>

export const adminCustomerSchema = z.object({
  id: z.string(),
  name: z.string().nullable().optional(),
  phone: z.string().optional(),
  email: z.string().nullable().optional(),
  appointment_count: z.number().optional(),
  last_appointment_at: z.string().nullable().optional(),
  notes: z.string().nullable().optional(),
})

export type AdminCustomer = z.infer<typeof adminCustomerSchema>

export const adminCustomersResponseSchema = z.object({
  count: z.number().optional().default(0),
  next: z.string().nullable().optional(),
  previous: z.string().nullable().optional(),
  results: z.array(adminCustomerSchema),
})

export type AdminCustomersResponse = z.infer<
  typeof adminCustomersResponseSchema
>

export const adminCustomerDetailSchema = adminCustomerSchema.extend({
  created_at: z.string().optional(),
})

export type AdminCustomerDetail = z.infer<typeof adminCustomerDetailSchema>

export const adminPaymentSchema = paymentSchema.extend({
  gateway_order_id: z.string().optional(),
  customer: adminCustomerRefSchema.optional(),
})

export type AdminPayment = z.infer<typeof adminPaymentSchema>

export const adminPaymentsResponseSchema = z.object({
  count: z.number().optional().default(0),
  next: z.string().nullable().optional(),
  previous: z.string().nullable().optional(),
  results: z.array(adminPaymentSchema),
})

export type AdminPaymentsResponse = z.infer<typeof adminPaymentsResponseSchema>

export const auditLogSchema = z.object({
  id: z.string(),
  actor_type: z.string().optional(),
  actor_id: z.string().optional(),
  action: z.string(),
  entity_type: z.string().optional(),
  entity_id: z.string().optional(),
  before: z.unknown().optional(),
  after: z.unknown().optional(),
  ip: z.string().optional(),
  created_at: z.string(),
})

export type AuditLog = z.infer<typeof auditLogSchema>

export const auditLogsResponseSchema = z.object({
  count: z.number().optional().default(0),
  next: z.string().nullable().optional(),
  previous: z.string().nullable().optional(),
  results: z.array(auditLogSchema),
})

export type AuditLogsResponse = z.infer<typeof auditLogsResponseSchema>

export const calendarBlockStatusSchema = z.enum([
  'available',
  'booked',
  'blocked',
])

export const adminCalendarEntrySchema = z.object({
  date: z.string().optional(),
  count: z.number().optional(),
  start_at: z.string().optional(),
  end_at: z.string().optional(),
  status: calendarBlockStatusSchema.optional().default('available'),
  appointment_id: z.string().optional(),
  service: adminServiceRefSchema.optional(),
  customer: adminCustomerRefSchema.optional(),
})

export type AdminCalendarEntry = z.infer<typeof adminCalendarEntrySchema>

export const adminCalendarResponseSchema = z.union([
  z.array(adminCalendarEntrySchema),
  z.object({
    view: z.string().optional(),
    from: z.string().optional(),
    to: z.string().optional(),
    entries: z.array(adminCalendarEntrySchema),
  }),
])

export type AdminCalendarResponse = z.infer<typeof adminCalendarResponseSchema>

export const adminServiceSchema = z.object({
  id: z.string(),
  name: z.string(),
  slug: z.string().optional(),
  description: z.string().nullable().optional(),
  duration_minutes: z.number().optional(),
  price: z.number().optional(),
  is_active: z.boolean().optional().default(true),
  sort_order: z.number().optional(),
  created_at: z.string().optional(),
})

export type AdminService = z.infer<typeof adminServiceSchema>

export const availabilityRuleSchema = z.object({
  id: z.string(),
  weekday: z.number().optional(),
  start_time: z.string().optional(),
  end_time: z.string().optional(),
  is_active: z.boolean().optional().default(true),
})

export type AvailabilityRule = z.infer<typeof availabilityRuleSchema>

export const availabilityExceptionSchema = z.object({
  id: z.string(),
  date: z.string().optional(),
  start_at: z.string().nullable().optional(),
  end_at: z.string().nullable().optional(),
  note: z.string().nullable().optional(),
  is_active: z.boolean().optional(),
})

export type AvailabilityException = z.infer<typeof availabilityExceptionSchema>

const asArray = <T extends z.ZodTypeAny>(item: T) =>
  z.union([z.array(item), z.object({ results: z.array(item) })])

export const adminServicesResponseSchema = asArray(adminServiceSchema)
export const availabilityRulesResponseSchema = asArray(availabilityRuleSchema)
export const availabilityExceptionsResponseSchema = asArray(
  availabilityExceptionSchema
)

export const refundStatusSchema = z.enum([
  'PENDING_ACTION',
  'SUCCEEDED',
  'FAILED',
])

export const adminRefundSchema = z.object({
  id: z.string(),
  payment: adminPaymentRefSchema.optional(),
  amount: z.number().catch(0),
  currency: z.string().optional().default('INR'),
  status: refundStatusSchema.optional().default('PENDING_ACTION'),
  reason: z.string().nullable().optional(),
  created_at: z.string().optional(),
  settled_at: z.string().nullable().optional(),
})

export type AdminRefund = z.infer<typeof adminRefundSchema>

export const adminRefundsResponseSchema = z.object({
  count: z.number().optional().default(0),
  next: z.string().nullable().optional(),
  previous: z.string().nullable().optional(),
  results: z.array(adminRefundSchema),
})

export type AdminRefundsResponse = z.infer<typeof adminRefundsResponseSchema>

export const faqItemSchema = z.object({
  question: z.string(),
  answer: z.string(),
})

export const workingHourSchema = z.object({
  weekday: z.number(),
  start_time: z.string(),
  end_time: z.string(),
})

export const adminSettingsSchema = z.object({
  business_name: z.string().optional().default(''),
  email: z.string().optional(),
  phone: z.string().optional(),
  address: z.string().nullable().optional(),
  about: z.string().nullable().optional(),
  timezone: z.string().optional().default('Asia/Kolkata'),
  currency: z.string().optional().default('INR'),
  faq: z.array(faqItemSchema).optional().default([]),
  reminder_offsets: z.array(z.number()).optional().default([]),
  cancellation_policy: z
    .object({
      window_hours: z.number().optional(),
      refund_percent: z.number().optional(),
    })
    .optional(),
  working_hours: z.array(workingHourSchema).optional().default([]),
})

export type AdminSettings = z.infer<typeof adminSettingsSchema>

export const appointmentReportSchema = z
  .object({
    count: z.number().catch(0),
    by_status: z.record(z.string(), z.number()).catch({}),
  })
  .or(
    z.object({
      groups: z
        .array(
          z.object({
            status: z.string().optional(),
            count: z.number().catch(0),
          })
        )
        .catch([]),
    })
  )

export type AppointmentReport = z.infer<typeof appointmentReportSchema>

export const revenueReportSchema = z.object({
  total: z.number().catch(0),
  currency: z.string().optional().default('INR'),
  series: z
    .array(
      z.object({
        period: z.string().optional(),
        date: z.string().optional(),
        amount: z.number().catch(0),
      })
    )
    .catch([]),
})

export type RevenueReport = z.infer<typeof revenueReportSchema>
