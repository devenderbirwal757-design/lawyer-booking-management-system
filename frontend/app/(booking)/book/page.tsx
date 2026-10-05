import type { Metadata } from 'next'
import { Suspense } from 'react'

import { BookingWizard } from '@/components/booking/booking-wizard'
import { getActiveServices } from '@/features/services/server-queries'

// Step 1 lists live services and prices, so the page cannot be prerendered: a
// static shell either froze the list at build time or shipped an error state
// when the API was unreachable during the build. Rendering per request keeps the
// service descriptions in the initial HTML, which is also what the page's
// largest text element is.
export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: 'Book a consultation',
  description:
    'Choose a service, pick a time that works for you, and pay securely online.',
  alternates: { canonical: '/book' },
  openGraph: {
    title: 'Book a consultation',
    description:
      'Choose a service, pick a time that works for you, and pay securely online.',
    url: '/book',
    type: 'website',
  },
  robots: { index: true, follow: true },
}

export default async function BookPage() {
  // Fetched on the server and handed to the wizard as `initialData` so step 1
  // is in the initial HTML. The wizard is a client component, so without this the
  // service list only appeared after the bundle booted and the API answered -
  // late enough to become the largest contentful paint.
  const result = await getActiveServices()

  return (
    <Suspense>
      <BookingWizard
        initialServices={result.ok ? result.services : undefined}
      />
    </Suspense>
  )
}
