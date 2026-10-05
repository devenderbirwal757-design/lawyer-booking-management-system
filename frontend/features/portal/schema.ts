import { z } from 'zod'

import {
  appointmentSchema,
  appointmentStatusSchema,
  paymentStatusSchema,
} from '@/features/booking/schema'

export const statusHistoryEntrySchema = z.object({
  from_status: appointmentStatusSchema.nullable().optional(),
  to_status: appointmentStatusSchema,
  actor: z.enum(['customer', 'admin', 'system']).optional(),
  note: z.string().optional(),
  created_at: z.string(),
})

export type StatusHistoryEntry = z.infer<typeof statusHistoryEntrySchema>

export const appointmentDetailSchema = appointmentSchema.extend({
  status_history: z.array(statusHistoryEntrySchema).default([]),
  cancellation_policy: z.string().optional(),
  refund_amount: z.number().nullable().optional(),
})

export type AppointmentDetail = z.infer<typeof appointmentDetailSchema>

export const meAppointmentsResponseSchema = z.object({
  count: z.number().optional().default(0),
  next: z.string().nullable().optional(),
  previous: z.string().nullable().optional(),
  results: z.array(appointmentDetailSchema),
})

export type MeAppointmentsResponse = z.infer<
  typeof meAppointmentsResponseSchema
>

export const paymentSchema = z.object({
  id: z.string(),
  appointment_id: z.string().optional(),
  order_id: z.string().optional(),
  gateway_payment_id: z.string().optional(),
  amount: z.number().int().min(0),
  currency: z.string().optional().default('INR'),
  status: paymentStatusSchema,
  paid_at: z.string().nullable().optional(),
  refunded_at: z.string().nullable().optional(),
  created_at: z.string().optional(),
})

export type Payment = z.infer<typeof paymentSchema>

export const mePaymentsResponseSchema = z.object({
  count: z.number().optional().default(0),
  next: z.string().nullable().optional(),
  previous: z.string().nullable().optional(),
  results: z.array(paymentSchema),
})

export type MePaymentsResponse = z.infer<typeof mePaymentsResponseSchema>

export const customerProfileSchema = z.object({
  id: z.string(),
  name: z.string().nullable().optional(),
  phone: z.string().optional(),
  email: z.string().nullable().optional(),
})

export type CustomerProfile = z.infer<typeof customerProfileSchema>

export const updateProfileSchema = z.object({
  name: z.string().trim().min(1, 'Enter your name').max(120, 'Too long'),
  email: z
    .string()
    .trim()
    .max(254)
    .email('Enter a valid email address')
    .optional()
    .or(z.literal('')),
})

export type UpdateProfile = z.infer<typeof updateProfileSchema>

export interface ProfilePatch {
  name?: string
  email?: string | null
  phone?: string
}
