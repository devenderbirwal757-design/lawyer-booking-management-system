import { describe, expect, it } from 'vitest'

import {
  adminMeSchema,
  customerMeSchema,
  sessionDisplayName,
} from '@/features/auth/schema'

/**
 * Regression coverage for the `/auth/me` contract.
 *
 * These payloads are verbatim responses from the running backend
 * (`AdminUserSerializer` and `CustomerProfileSerializer`). They exist because
 * the frontend previously declared `id: string` and `role: 'customer' |
 * 'admin'`, which matched nothing: `safeParse` rejected every real response,
 * `getSession()` returned `null`, and every authenticated route silently
 * redirected back to the login page.
 */

const adminPayload = {
  id: 4,
  email: 'boss@example.com',
  full_name: 'Demo',
  role: 'OWNER',
  is_active: true,
  is_staff: true,
  date_joined: '2026-09-28T22:24:51.705098+05:30',
  tenant: {
    id: 'f3960753-8e80-46ab-a46e-66db8f1dd562',
    name: 'Demo',
    slug: 'demo',
    timezone: 'UTC',
    currency: 'INR',
    status: 'ACTIVE',
  },
}

const customerPayload = {
  id: 9,
  phone: '+919876500077',
  name: 'E2E Tester',
  email: 'e2e@example.com',
  is_active: true,
  created_at: '2026-10-02T00:00:00Z',
}

describe('adminMeSchema', () => {
  it('accepts the AdminUserSerializer payload', () => {
    const parsed = adminMeSchema.safeParse(adminPayload)
    expect(parsed.success, JSON.stringify(parsed.error?.issues)).toBe(true)
  })

  it('treats the numeric primary key as the id', () => {
    const parsed = adminMeSchema.safeParse(adminPayload)
    expect(parsed.success && parsed.data.id).toBe(4)
  })

  it.each(['OWNER', 'ADMIN', 'STAFF', 'VIEWER'] as const)(
    'accepts the %s role',
    (role) => {
      expect(adminMeSchema.safeParse({ ...adminPayload, role }).success).toBe(true)
    }
  )

  it('rejects a lowercase role, which the backend never emits', () => {
    expect(adminMeSchema.safeParse({ ...adminPayload, role: 'owner' }).success).toBe(
      false
    )
  })

  it('rejects a customer payload', () => {
    expect(adminMeSchema.safeParse(customerPayload).success).toBe(false)
  })
})

describe('customerMeSchema', () => {
  it('accepts the CustomerProfileSerializer payload', () => {
    const parsed = customerMeSchema.safeParse(customerPayload)
    expect(parsed.success, JSON.stringify(parsed.error?.issues)).toBe(true)
  })

  it('rejects an admin payload', () => {
    expect(customerMeSchema.safeParse(adminPayload).success).toBe(false)
  })

  it('requires a phone', () => {
    const missingPhone: Record<string, unknown> = { ...customerPayload }
    delete missingPhone.phone
    expect(customerMeSchema.safeParse(missingPhone).success).toBe(false)
  })
})

describe('sessionDisplayName', () => {
  it('reads full_name for an admin', () => {
    const parsed = adminMeSchema.parse(adminPayload)
    expect(sessionDisplayName(parsed)).toBe('Demo')
  })

  it('reads name for a customer', () => {
    const parsed = customerMeSchema.parse(customerPayload)
    expect(sessionDisplayName(parsed)).toBe('E2E Tester')
  })

  it('falls back to the email when the name is blank', () => {
    const parsed = customerMeSchema.parse({ ...customerPayload, name: '   ' })
    expect(sessionDisplayName(parsed)).toBe('e2e@example.com')
  })
})
