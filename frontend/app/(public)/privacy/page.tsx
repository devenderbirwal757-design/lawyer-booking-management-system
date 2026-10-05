import type { Metadata } from 'next'

import { siteConfig } from '@/lib/constants/site'

export const metadata: Metadata = {
  title: 'Privacy Policy',
  description:
    'What we collect when you book, why we collect it, and how long we keep it.',
  alternates: { canonical: '/privacy' },
}

export default function PrivacyPage() {
  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-12">
      <h1 className="font-serif text-3xl tracking-tight">Privacy Policy</h1>
      <div className="mt-6 flex flex-col gap-6 text-sm leading-relaxed text-muted-foreground">
        <section>
          <h2 className="mb-2 font-medium text-foreground">What we collect</h2>
          <p>
            We collect the name, phone number, and, when you choose to provide
            it, email address you enter when booking. We also keep records of
            your consultations and payments.
          </p>
        </section>
        <section>
          <h2 className="mb-2 font-medium text-foreground">Why we use it</h2>
          <p>
            Your details are used to manage your bookings, send confirmations
            and reminders, and provide the services you request. We do not sell
            your data.
          </p>
        </section>
        <section>
          <h2 className="mb-2 font-medium text-foreground">Your choices</h2>
          <p>
            You can request access to, correction of, or deletion of your
            personal information at any time by contacting{' '}
            <a
              href={`mailto:${siteConfig.contact.email}`}
              className="text-primary underline underline-offset-4"
            >
              {siteConfig.contact.email}
            </a>
            .
          </p>
        </section>
      </div>
    </div>
  )
}
