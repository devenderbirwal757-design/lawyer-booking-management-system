import type { Metadata } from 'next'

import { AdminShell } from '@/components/admin/admin-shell'

import { requireAdmin } from '@/lib/auth/session'

export const metadata: Metadata = {
  robots: { index: false, follow: false },
}

export default async function AdminShellLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const session = await requireAdmin()
  return <AdminShell email={session?.email ?? undefined}>{children}</AdminShell>
}
