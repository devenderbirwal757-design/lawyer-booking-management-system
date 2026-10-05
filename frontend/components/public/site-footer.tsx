import Link from 'next/link'

import { MailIcon, MapPinIcon, PhoneIcon } from 'lucide-react'

import { siteConfig } from '@/lib/constants/site'

const legalLinks = [
  { label: 'Terms of Service', href: '/terms' },
  { label: 'Privacy Policy', href: '/privacy' },
  { label: 'FAQ', href: '/#faq' },
]

export function SiteFooter() {
  return (
    <footer className="border-t border-border bg-muted/30">
      <div className="mx-auto grid w-full max-w-6xl gap-8 px-4 py-12 md:grid-cols-[1.4fr_1fr_1fr]">
        <div className="flex flex-col gap-3">
          <p className="font-serif text-lg font-semibold">{siteConfig.brand}</p>
          <p className="max-w-sm text-sm text-muted-foreground">
            {siteConfig.description}
          </p>
        </div>

        <div className="flex flex-col gap-2 text-sm">
          <p className="font-medium">Contact</p>
          <a
            href={`mailto:${siteConfig.contact.email}`}
            className="flex items-center gap-2 text-muted-foreground transition-colors hover:text-foreground"
          >
            <MailIcon className="size-4" />
            {siteConfig.contact.email}
          </a>
          <a
            href={`tel:${siteConfig.contact.phone}`}
            className="flex items-center gap-2 text-muted-foreground transition-colors hover:text-foreground"
          >
            <PhoneIcon className="size-4" />
            {siteConfig.contact.phone}
          </a>
          <span className="flex items-start gap-2 text-muted-foreground">
            <MapPinIcon className="mt-0.5 size-4 shrink-0" />
            {siteConfig.contact.address}
          </span>
        </div>

        <div className="flex flex-col gap-2 text-sm">
          <p className="font-medium">Legal</p>
          {legalLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="text-muted-foreground transition-colors hover:text-foreground"
            >
              {link.label}
            </Link>
          ))}
        </div>
      </div>

      <div className="border-t border-border">
        <div className="mx-auto flex w-full max-w-6xl flex-col items-center justify-between gap-2 px-4 py-5 text-xs text-muted-foreground sm:flex-row">
          <p>
            © {new Date().getFullYear()} {siteConfig.legalName}. All rights
            reserved.
          </p>
          <p>{siteConfig.profile.role}</p>
        </div>
      </div>
    </footer>
  )
}
