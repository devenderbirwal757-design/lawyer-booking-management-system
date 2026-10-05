import Link from 'next/link'

import { Button } from '@/components/ui/button'

export function Cta() {
  return (
    <section className="mx-auto w-full max-w-6xl px-4 py-16">
      <div className="flex flex-col items-center gap-4 rounded-2xl bg-primary px-6 py-12 text-center text-primary-foreground">
        <h2 className="font-serif text-3xl tracking-tight">
          Have a question about your matter?
        </h2>
        <p className="max-w-xl text-sm text-primary-foreground/80">
          Choose a service and pick a time that works for you. Your slot is
          confirmed the moment payment succeeds.
        </p>
        <Button asChild size="lg" variant="secondary" className="mt-2">
          <Link href="/book">Book a consultation</Link>
        </Button>
      </div>
    </section>
  )
}
