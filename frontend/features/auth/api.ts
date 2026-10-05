import { useQuery } from '@tanstack/react-query'

import { api } from '@/lib/api/client'
import { endpoints } from '@/lib/api/endpoints'
import { queryKeys } from '@/lib/api/query-keys'
import { clearSession, setSession, toTokenPair } from '@/lib/auth/token-store'
import type {
  AdminLogin,
  AdminSession,
  CustomerSession,
  OtpRequest,
  OtpVerify,
} from '@/features/auth/schema'

/** Fail loudly rather than silently "logging in" without a usable session. */
function adoptSession(response: unknown, context: string): void {
  const pair = toTokenPair(response)
  if (!pair) {
    throw new Error(`${context} did not return a token pair.`)
  }
  setSession(pair)
}

export async function requestOtp(phone: OtpRequest['phone']): Promise<void> {
  await api.post<unknown>(endpoints.auth.otpRequest, { phone })
}

/**
 * The backend answers with a token pair in the body and sets no cookie, so the
 * pair is adopted here. Without this the Next route guard sees no session
 * cookies and bounces the user straight back to the login page.
 */
export async function verifyOtp(
  payload: Omit<OtpVerify, 'phone'> & { phone: string }
): Promise<void> {
  const response = await api.post<unknown>(endpoints.auth.otpVerify, payload)
  adoptSession(response, 'OTP verification')
}

export async function loginAdmin(credentials: AdminLogin): Promise<void> {
  const response = await api.post<unknown>(endpoints.auth.adminLogin, credentials)
  adoptSession(response, 'admin login')
}

export async function logoutAdmin(): Promise<void> {
  try {
    await api.post<unknown>(endpoints.auth.adminLogout)
  } finally {
    // Clear locally even if the call fails: leaving a stale cookie would keep
    // the user stuck behind a guard they cannot pass.
    clearSession()
  }
}

export async function logoutCustomer(): Promise<void> {
  try {
    await api.post<unknown>(endpoints.auth.customerLogout)
  } finally {
    clearSession()
  }
}

export function useMe() {
  return useQuery({
    queryKey: queryKeys.auth.me,
    queryFn: () => api.get<CustomerSession | AdminSession>(endpoints.auth.me),
    staleTime: 30_000,
    retry: false,
  })
}

export type { CustomerSession }
