import Link from 'next/link'
import { CheckIcon, ScaleIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { siteConfig } from '@/lib/constants/site'

export function Hero() {
  const { profile } = siteConfig

  return (
    <section id="about" className="border-b border-border bg-muted/40">
      <div className="mx-auto grid w-full max-w-6xl gap-10 px-4 py-16 md:grid-cols-[1.2fr_0.8fr] md:items-center md:py-24">
        <div className="flex flex-col gap-6">
          <div className="flex items-center gap-2 text-sm font-medium text-primary">
            <ScaleIcon className="size-4" />
            {profile.role}
          </div>
          <h1 className="font-serif text-4xl leading-tight tracking-tight md:text-5xl">
            {profile.name}
          </h1>
          <p className="max-w-xl text-base text-muted-foreground md:text-lg">
            {profile.summary}
          </p>

          <ul className="flex flex-col gap-2 text-sm text-muted-foreground">
            {profile.highlights.map((highlight) => (
              <li key={highlight} className="flex items-start gap-2">
                <CheckIcon className="mt-0.5 size-4 shrink-0 text-primary" />
                {highlight}
              </li>
            ))}
          </ul>

          <div className="flex flex-wrap gap-3">
            <Button asChild size="lg">
              <Link href="/book">Book a consultation</Link>
            </Button>
            <Button asChild size="lg" variant="outline">
              <Link href="/services">View services &amp; pricing</Link>
            </Button>
          </div>
        </div>

        <div className="hidden justify-center md:flex" aria-hidden>
          <div className="flex size-64 items-center justify-center rounded-2xl bg-primary font-serif text-7xl text-primary-foreground shadow-lg">
            AS
          </div>
        </div>
      </div>
    </section>
  )
}
