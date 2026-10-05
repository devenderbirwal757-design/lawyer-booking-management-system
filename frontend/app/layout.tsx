import type { Metadata } from 'next'
import { Geist, Geist_Mono, Lora } from 'next/font/google'

import { Providers } from '@/app/providers'
import { OfflineBanner } from '@/components/shared/offline-banner'
import { siteConfig } from '@/lib/constants/site'

import './globals.css'

/**
 * `font-display: optional` rather than the `swap` default.
 *
 * With `swap`, the browser paints the fallback face first and then repaints the
 * text when the webfont arrives. That second paint is a *new* largest
 * contentful paint candidate, so LCP landed on font download time rather than on
 * when the content was actually ready: 3.2s on `/` and `/services` and 4.1s on
 * `/book`, against a §8 budget of 2.5s. `optional` gives the font a short block
 * period and, if it misses, keeps the fallback for that page load instead of
 * repainting - so the first paint is the LCP. Repeat visits get the real face
 * from cache.
 */
const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
  display: 'optional',
})

// Mono is only used on admin/customer detail screens and the confirmation step,
// never on the public or booking routes, so preloading it there just competes
// for bandwidth with the fonts that do paint above the fold.
const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
  display: 'optional',
  preload: false,
})

const serif = Lora({
  variable: '--font-serif',
  subsets: ['latin'],
  display: 'optional',
})

const baseUrl = new URL(siteConfig.url)

export const metadata: Metadata = {
  metadataBase: baseUrl,
  title: {
    default: siteConfig.name,
    template: `%s · ${siteConfig.name}`,
  },
  description: siteConfig.description,
  openGraph: {
    title: siteConfig.name,
    description: siteConfig.description,
    url: baseUrl,
    siteName: siteConfig.name,
    type: 'website',
    locale: 'en_IN',
  },
  twitter: {
    card: 'summary_large_image',
    title: siteConfig.name,
    description: siteConfig.description,
  },
  // No canonical here on purpose: every indexable route declares its own, and a
  // canonical inherited by the noindex routes would contradict their robots tag.
  robots: {
    index: true,
    follow: true,
  },
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        className={`${geistSans.variable} ${geistMono.variable} ${serif.variable} font-sans antialiased`}
      >
        <Providers>
          <OfflineBanner />
          {children}
        </Providers>
      </body>
    </html>
  )
}
