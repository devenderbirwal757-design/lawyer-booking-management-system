import { z } from 'zod'

import { serviceSchema } from '@/features/services/schema'

export const availabilityDatesSchema = z.union([
  z.array(z.string()),
  z.object({
    month: z.string().optional(),
    dates: z.array(z.string()),
  }),
])

export type AvailabilityDates = z.infer<typeof availabilityDatesSchema>

const slotTimes = z.union([
  z.array(z.string()),
  z.array(z.object({ start_at: z.string() })),
  z.array(
    z.object({
      start_at: z.string(),
      end_at: z.string().optional(),
    })
  ),
])

export const availabilitySlotsSchema = z.union([
  slotTimes,
  z.object({
    date: z.string().optional(),
    slots: slotTimes,
  }),
])

export type RawAvailabilitySlot = z.infer<typeof slotTimes>[number]

export const appointmentStatusSchema = z.enum([
  'PENDING_PAYMENT',
  'CONFIRMED',
  'CANCELLED',
  'COMPLETED',
  'NO_SHOW',
  'RESCHEDULED',
  'EXPIRED',
])

export type AppointmentStatus = z.infer<typeof appointmentStatusSchema>

export const paymentStatusSchema = z.enum([
  'CREATED',
  'PENDING',
  'SUCCESS',
  'FAILED',
  'EXPIRED',
  'CANCELLED',
  'REFUNDED',
])

export type PaymentStatus = z.infer<typeof paymentStatusSchema>

export const appointmentSchema = z.object({
  id: z.string(),
  status: appointmentStatusSchema,
  service: serviceSchema.partial().required({ id: true }),
  customer: z
    .object({
      name: z.string().optional(),
      phone: z.string().optional(),
      email: z.string().nullable().optional(),
    })
    .optional(),
  start_at: z.string(),
  end_at: z.string().optional(),
  timezone: z.string().optional(),
  slot_hold_expires_at: z.string().nullable().optional(),
  payment: z
    .object({
      order_id: z.string().optional(),
      payment_order_id: z.string().optional(),
      status: z.string().optional(),
    })
    .optional(),
  payment_order_id: z.string().optional(),
  gateway_order_id: z.string().optional(),
})

export type Appointment = z.infer<typeof appointmentSchema>

export const paymentOrderSchema = z.object({
  payment_order_id: z.string().optional(),
  appointment_id: z.string().optional(),
  gateway_order_id: z.string(),
  // Amount in rupees for display; `amount_minor` is the paise value passed to Razorpay.
  amount: z.number().int().min(0),
  amount_minor: z.number().int().min(0).optional(),
  currency: z.string().default('INR'),
  key_id: z.string().optional(),
  // Backend may expose `gateway_key_id` instead of `key_id`; the UI reads both.
  gateway_key_id: z.string().optional(),
})

export type PaymentOrder = z.infer<typeof paymentOrderSchema>

export const bookingDetailsSchema = z.object({
  name: z.string().trim().min(1, 'Enter your name').max(120, 'Too long'),
  phone: z
    .string()
    .trim()
    .regex(/^[6-9]\d{9}$/, 'Enter a valid 10-digit mobile number'),
  email: z
    .string()
    .trim()
    .email('Enter a valid email address')
    .max(254)
    .optional()
    .or(z.literal('')),
  notes: z
    .string()
    .trim()
    .max(500, 'Keep notes under 500 characters')
    .optional(),
})

export type BookingDetails = z.infer<typeof bookingDetailsSchema>

export const createAppointmentPayloadSchema = z.object({
  service_id: z.string(),
  start_at: z.string(),
  customer_notes: z.string().optional(),
})

export type CreateAppointmentPayload = z.infer<
  typeof createAppointmentPayloadSchema
>

export const createOrderPayloadSchema = z.object({
  appointment_id: z.string(),
})

export type CreateOrderPayload = z.infer<typeof createOrderPayloadSchema>
