import { z } from 'zod'

const serviceStatusSchema = z.enum(['active', 'inactive', 'archived'])

export const serviceSchema = z.object({
  id: z.string().min(1),
  slug: z.string().min(1),
  name: z.string().min(1),
  description: z.string().default(''),
  duration_minutes: z.number().int().positive(),
  price_amount: z.coerce.number().nonnegative(),
  currency: z.string().default('INR'),
  status: serviceStatusSchema.default('active'),
  requires_payment: z.boolean().default(true),
})

export type Service = z.infer<typeof serviceSchema>
export type ServiceStatus = z.infer<typeof serviceStatusSchema>

export const serviceListPageSchema = z.object({
  count: z.number(),
  next: z.string().nullable(),
  previous: z.string().nullable(),
  results: z.array(serviceSchema),
})

export type ServiceListPage = z.infer<typeof serviceListPageSchema>
