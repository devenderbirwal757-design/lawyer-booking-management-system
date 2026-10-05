'use client'

import {
  CalendarDaysIcon,
  CalendarRangeIcon,
  CreditCardIcon,
  FileClockIcon,
  LayoutDashboardIcon,
  ReceiptTextIcon,
  ScrollTextIcon,
  SettingsIcon,
  UsersIcon,
} from 'lucide-react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'

import { cn } from 'cn'

export interface AdminNavItem {
  href: string
  label: string
  icon: React.ComponentType<React.SVGProps<SVGSVGElement>>
  disabled?: boolean
}

export const ADMIN_NAV: AdminNavItem[] = [
  { href: '/admin/dashboard', label: 'Dashboard', icon: LayoutDashboardIcon },
  {
    href: '/admin/appointments',
    label: 'Appointments',
    icon: CalendarRangeIcon,
  },
  { href: '/admin/calendar', label: 'Calendar', icon: CalendarDaysIcon },
  { href: '/admin/clients', label: 'Clients', icon: UsersIcon },
  { href: '/admin/services', label: 'Services', icon: CreditCardIcon },
  { href: '/admin/payments', label: 'Payments', icon: ReceiptTextIcon },
  { href: '/admin/reports', label: 'Reports', icon: FileClockIcon },
  { href: '/admin/audit', label: 'Audit', icon: ScrollTextIcon },
  { href: '/admin/settings', label: 'Settings', icon: SettingsIcon },
]

export function AdminNavItemLink({
  item,
  dismiss,
}: {
  item: AdminNavItem
  dismiss?: () => void
}) {
  const pathname = usePathname()
  const active = pathname === item.href || pathname.startsWith(`${item.href}/`)
  const Icon = item.icon

  const classes = cn(
    'flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
    active
      ? 'bg-primary text-primary-foreground'
      : item.disabled
        ? 'cursor-not-allowed text-muted-foreground/50'
        : 'text-muted-foreground hover:bg-muted hover:text-foreground'
  )

  if (item.disabled) {
    return (
      <span
        aria-disabled="true"
        title="Coming in a later phase"
        className={classes}
      >
        <Icon className="size-4" />
        {item.label}
      </span>
    )
  }

  return (
    <Link href={item.href} onClick={dismiss} className={classes}>
      <Icon className="size-4" />
      {item.label}
    </Link>
  )
}
