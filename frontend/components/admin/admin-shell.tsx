'use client'

import { Loader2Icon, LogOutIcon, MenuIcon } from 'lucide-react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useState } from 'react'

import { ADMIN_NAV, AdminNavItemLink } from '@/components/admin/admin-nav'
import { Button } from '@/components/ui/button'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'

import { logoutAdmin } from '@/features/auth/api'

export function AdminShell({
  email,
  children,
}: {
  email?: string
  children: React.ReactNode
}) {
  const pathname = usePathname()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [signingOut, setSigningOut] = useState(false)

  const sectionLabel =
    ADMIN_NAV.find(
      (item) => pathname === item.href || pathname.startsWith(`${item.href}/`)
    )?.label ?? 'Admin'

  const handleSignOut = async () => {
    setSigningOut(true)
    try {
      await logoutAdmin()
    } finally {
      window.location.assign('/admin/login')
    }
  }

  return (
    <div className="flex min-h-dvh bg-muted/30">
      <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col border-r border-border bg-background lg:flex">
        <div className="flex h-14 items-center border-b border-border px-4">
          <Link
            href="/admin/dashboard"
            className="font-serif text-lg font-semibold tracking-tight"
          >
            Admin
          </Link>
        </div>
        <nav aria-label="Admin" className="flex flex-1 flex-col gap-1 p-3">
          {ADMIN_NAV.map((item) => (
            <AdminNavItemLink key={item.href} item={item} />
          ))}
        </nav>
        <div className="border-t border-border p-3">
          {email ? (
            <p className="mb-2 truncate px-3 text-xs text-muted-foreground">
              {email}
            </p>
          ) : null}
          <Button
            variant="ghost"
            size="sm"
            className="w-full justify-start"
            disabled={signingOut}
            onClick={() => void handleSignOut()}
          >
            {signingOut ? (
              <Loader2Icon className="size-4 animate-spin" />
            ) : (
              <LogOutIcon className="size-4" />
            )}
            Sign out
          </Button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between gap-3 border-b border-border bg-background px-4">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="icon"
              className="lg:hidden"
              aria-label="Open menu"
              onClick={() => setDrawerOpen(true)}
            >
              <MenuIcon className="size-5" />
            </Button>
            <span className="text-sm font-semibold">{sectionLabel}</span>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="lg:hidden"
            disabled={signingOut}
            onClick={() => void handleSignOut()}
          >
            {signingOut ? (
              <Loader2Icon className="size-4 animate-spin" />
            ) : (
              <LogOutIcon className="size-4" />
            )}
            Sign out
          </Button>
        </header>

        <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">
          {children}
        </main>
      </div>

      <Sheet open={drawerOpen} onOpenChange={setDrawerOpen}>
        <SheetContent side="left" className="w-64">
          <SheetHeader>
            <SheetTitle>Admin</SheetTitle>
          </SheetHeader>
          <nav aria-label="Admin" className="mt-4 flex flex-col gap-1">
            {ADMIN_NAV.map((item) => (
              <AdminNavItemLink
                key={item.href}
                item={item}
                dismiss={() => {
                  setDrawerOpen(false)
                }}
              />
            ))}
          </nav>
        </SheetContent>
      </Sheet>
    </div>
  )
}
