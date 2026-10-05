import Link from 'next/link'

import { siteConfig } from '@/lib/constants/site'

export default function BookingLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div className="flex min-h-dvh flex-col bg-muted/30">
      <header className="sticky top-0 z-20 border-b border-border bg-background">
        <div className="mx-auto flex w-full max-w-3xl items-center justify-between px-4 py-3">
          <Link
            href="/"
            className="font-serif text-lg font-semibold tracking-tight"
          >
            {siteConfig.brand}
          </Link>
          <Link
            href="/"
            className="text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            ← Back to site
          </Link>
        </div>
      </header>

      <main className="flex-1">{children}</main>
    </div>
  )
}
