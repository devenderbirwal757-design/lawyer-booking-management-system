import { z } from 'zod'

const phone = z
  .string()
  .trim()
  .regex(/^[6-9]\d{9}$/, 'Enter a valid 10-digit mobile number')

export const otpRequestSchema = z.object({
  phone,
})

export const otpVerifySchema = z.object({
  phone,
  code: z
    .string()
    .trim()
    .regex(/^\d{6}$/, 'Enter the 6-digit code'),
  name: z.string().trim().min(1).max(120).optional(),
  email: z.string().trim().email().max(254).optional(),
})

export const adminLoginSchema = z.object({
  email: z.string().trim().email().max(254),
  password: z.string().min(8, 'Password is required'),
})

/**
 * `GET /auth/me` returns whichever profile matches the token, so there is no
 * single `role` field to switch on - the two payloads only overlap on `id` and
 * `email`. These match the backend serializers exactly:
 *
 *  - `CustomerProfileSerializer` -> `id, phone, name, email, is_active, created_at`
 *  - `AdminUserSerializer`       -> `id, email, full_name, role, is_active,
 *                                    is_staff, date_joined, tenant`
 *
 * IDs are Django primary keys (numbers), and admin roles are the uppercase
 * model choices `OWNER | ADMIN | STAFF | VIEWER` - see
 * `backend/apps/accounts/serializers.py`. A previous version of this file
 * declared `id: string` and `role: 'customer' | 'admin'`, which no response has
 * ever matched: `safeParse` failed, `getSession()` returned null, and every
 * authenticated route bounced back to the login page.
 */
export const customerMeSchema = z.object({
  id: z.number(),
  phone: z.string(),
  name: z.string().nullable().optional(),
  email: z.string().nullable().optional(),
  is_active: z.boolean().optional(),
})

export const adminMeSchema = z.object({
  id: z.number(),
  email: z.string(),
  full_name: z.string().nullable().optional(),
  role: z.enum(['OWNER', 'ADMIN', 'STAFF', 'VIEWER']),
  is_active: z.boolean().optional(),
  is_staff: z.boolean().optional(),
  tenant: z
    .object({
      id: z.string(),
      name: z.string(),
      slug: z.string(),
      timezone: z.string().optional(),
      currency: z.string().optional(),
      status: z.string().optional(),
    })
    .optional(),
})

/**
 * Display name for either profile, since the field is `name` on one side and
 * `full_name` on the other. `phone` only exists on the customer payload, so it
 * discriminates the union.
 */
export function sessionDisplayName(
  session: AdminSession | CustomerSession
): string {
  if ('phone' in session) {
    return session.name?.trim() || session.email || ''
  }
  return session.full_name?.trim() || session.email || ''
}

export type OtpRequest = z.infer<typeof otpRequestSchema>
export type OtpVerify = z.infer<typeof otpVerifySchema>
export type AdminLogin = z.infer<typeof adminLoginSchema>
export type CustomerSession = z.infer<typeof customerMeSchema>
export type AdminSession = z.infer<typeof adminMeSchema>
