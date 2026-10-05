import 'server-only'

import { headers } from 'next/headers'
import { redirect } from 'next/navigation'
import { cache } from 'react'

import { API_BASE_URL } from '@/lib/api/client'
import { endpoints } from '@/lib/api/endpoints'
import { SESSION_COOKIES } from '@/lib/auth/cookies'
import {
  adminMeSchema,
  customerMeSchema,
  type AdminSession,
  type CustomerSession,
} from '@/features/auth/schema'

/**
 * `/auth/me` serves whichever profile matches the token, and the two payloads
 * share only `id` and `email`, so they are parsed as a union and discriminated
 * by shape: an admin payload always carries `role`, a customer payload always
 * carries `phone`. The schemas live in `features/auth/schema.ts` next to the
 * types so the client and server cannot drift.
 */
export type Session = AdminSession | CustomerSession

function parseSession(payload: unknown): Session | null {
  const admin = adminMeSchema.safeParse(payload)
  if (admin.success) return admin.data
  const customer = customerMeSchema.safeParse(payload)
  return customer.success ? customer.data : null
}

export const getSession = cache(async (): Promise<Session | null> => {
  const headerStore = await headers()
  const cookieHeader = headerStore.get('cookie')
  if (!cookieHeader) {
    return null
  }

  const accessCookie = cookieValue(cookieHeader, SESSION_COOKIES[0])
  const hasToken = SESSION_COOKIES.some((name) =>
    new RegExp(`(?:^|;)\\s*${name}=`).test(cookieHeader)
  )
  if (!hasToken) {
    return null
  }

  try {
    const res = await fetch(`${API_BASE_URL}${endpoints.auth.me}`, {
      headers: {
        cookie: cookieHeader,
        // The backend authenticates with `Authorization: Bearer` only - a bare
        // cookie is rejected - so the mirrored token has to be promoted to a
        // bearer header here. `lib/auth/token-store` is what put it in the
        // cookie in the first place.
        ...(accessCookie ? { authorization: `Bearer ${accessCookie}` } : {}),
      },
      next: { revalidate: 0 },
    })
    if (!res.ok) {
      return null
    }
    return parseSession(await res.json())
  } catch {
    return null
  }
})

function cookieValue(cookieHeader: string, name: string): string | null {
  const match = new RegExp(`(?:^|;\\s*)${name}=([^;]*)`).exec(cookieHeader)
  return match ? decodeURIComponent(match[1]) : null
}

export function isCustomerSession(
  session: Session | null
): session is CustomerSession {
  return customerMeSchema.safeParse(session).success
}

export function isAdminSession(session: Session | null): session is AdminSession {
  return adminMeSchema.safeParse(session).success
}

export async function requireCustomer(): Promise<Session> {
  const session = await getSession()
  if (!isCustomerSession(session)) {
    redirect('/login')
  }
  return session
}

export async function requireAdmin(): Promise<Session> {
  const session = await getSession()
  if (!isAdminSession(session)) {
    redirect('/admin/login')
  }
  return session
}
