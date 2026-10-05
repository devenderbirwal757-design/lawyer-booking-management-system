import type { Metadata } from 'next'
import { redirect } from 'next/navigation'
import { Suspense } from 'react'

import { CustomerLogin } from '@/components/auth/customer-login'
import { getSession, isCustomerSession } from '@/lib/auth/session'

export const metadata: Metadata = {
  title: 'Sign in',
  robots: { index: false, follow: false },
}

export default async function LoginPage() {
  const session = await getSession()
  if (isCustomerSession(session)) {
    redirect('/')
  }

  return (
    <Suspense>
      <CustomerLogin />
    </Suspense>
  )
}
