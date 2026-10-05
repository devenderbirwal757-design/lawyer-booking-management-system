'use client'

import { Loader2Icon } from 'lucide-react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { cn } from 'cn'

import { logoutCustomer, useMe } from '@/features/auth/api'

const NAV = [
  { href: '/dashboard', label: 'Dashboard' },
  { href: '/payments', label: 'Payments' },
  { href: '/profile', label: 'Profile' },
]

export function CustomerShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const me = useMe()
  const [signingOut, setSigningOut] = useState(false)

  const handleLogout = async () => {
    setSigningOut(true)
    try {
      await logoutCustomer()
    } catch {
      // The backend may reject the logout cookie; sign out locally either way.
    } finally {
      window.sessionStorage.removeItem('booking-draft')
      window.location.assign('/')
    }
  }

  return (
    <div className="flex min-h-dvh flex-col bg-muted/30">
      <header className="sticky top-0 z-20 border-b border-border bg-background">
        <div className="mx-auto flex w-full max-w-4xl items-center justify-between gap-4 px-4 py-3">
          <Link
            href="/"
            className="font-serif text-lg font-semibold tracking-tight"
          >
            Client portal
          </Link>

          <nav
            aria-label="Client portal"
            className="hidden items-center gap-1 sm:flex"
          >
            {NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                aria-current={
                  pathname === item.href || pathname.startsWith(`${item.href}/`)
                    ? 'page'
                    : undefined
                }
                className={cn(
                  'rounded-lg px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground',
                  pathname === item.href || pathname.startsWith(`${item.href}/`)
                    ? 'bg-muted font-medium text-foreground'
                    : undefined
                )}
              >
                {item.label}
              </Link>
            ))}
          </nav>

          <div className="flex items-center gap-3">
            {me.data && 'phone' in me.data && me.data.phone ? (
              <span className="hidden text-sm text-muted-foreground md:inline">
                +91 {me.data.phone}
              </span>
            ) : null}
            <Button
              variant="ghost"
              size="sm"
              disabled={signingOut}
              onClick={() => void handleLogout()}
            >
              {signingOut ? (
                <Loader2Icon className="size-4 animate-spin" />
              ) : null}
              Sign out
            </Button>
          </div>
        </div>

        <nav
          aria-label="Client portal"
          className="flex items-center gap-1 overflow-x-auto px-4 pb-2 sm:hidden"
        >
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              aria-current={
                pathname === item.href || pathname.startsWith(`${item.href}/`)
                  ? 'page'
                  : undefined
              }
              className={cn(
                'rounded-lg px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground',
                pathname === item.href || pathname.startsWith(`${item.href}/`)
                  ? 'bg-muted font-medium text-foreground'
                  : undefined
              )}
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </header>

      <main className="mx-auto w-full max-w-4xl flex-1 px-4 py-8">
        {children}
      </main>
    </div>
  )
}
