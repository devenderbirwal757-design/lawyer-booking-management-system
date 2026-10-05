import type { Metadata } from 'next'

import { siteConfig } from '@/lib/constants/site'

export const metadata: Metadata = {
  title: 'Terms of Service',
  description:
    'The terms that apply when you book a consultation through this website, including cancellations and refunds.',
  alternates: { canonical: '/terms' },
}

export default function TermsPage() {
  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-12">
      <h1 className="font-serif text-3xl tracking-tight">Terms of Service</h1>
      <div className="mt-6 flex flex-col gap-6 text-sm leading-relaxed text-muted-foreground">
        <section>
          <h2 className="mb-2 font-medium text-foreground">1. These terms</h2>
          <p>
            Booking a consultation through this website forms an agreement
            between you and {siteConfig.legalName} on the terms below. Please
            read them before making a booking.
          </p>
        </section>
        <section>
          <h2 className="mb-2 font-medium text-foreground">2. Bookings</h2>
          <p>
            A consultation is only confirmed once your payment is successful.
            Bookings are subject to our cancellation and rescheduling policy.
          </p>
        </section>
        <section>
          <h2 className="mb-2 font-medium text-foreground">3. Payments</h2>
          <p>
            Fees are shown in the service catalogue before you pay. Payments are
            processed by a regulated payment gateway. A receipt is available
            after confirmation.
          </p>
        </section>
        <section>
          <h2 className="mb-2 font-medium text-foreground">4. Liability</h2>
          <p>
            Consultations provide general legal guidance, not a legal opinion
            addressed to your specific dispute, unless otherwise agreed in
            writing.
          </p>
        </section>
      </div>
    </div>
  )
}
