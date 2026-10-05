import { ClockIcon, MailIcon, MapPinIcon, PhoneIcon } from 'lucide-react'

import { siteConfig } from '@/lib/constants/site'

export function ContactSection() {
  const { contact } = siteConfig

  const items = [
    {
      icon: MailIcon,
      label: 'Email',
      value: contact.email,
      href: `mailto:${contact.email}`,
    },
    {
      icon: PhoneIcon,
      label: 'Phone',
      value: contact.phone,
      href: `tel:${contact.phone}`,
    },
    { icon: MapPinIcon, label: 'Chambers', value: contact.address },
    { icon: ClockIcon, label: 'Hours', value: contact.hours },
  ]

  return (
    <section id="contact" className="border-t border-border bg-muted/40">
      <div className="mx-auto w-full max-w-6xl px-4 py-16">
        <div className="mb-8 flex flex-col gap-2">
          <p className="text-sm font-medium text-primary">Reach out</p>
          <h2 className="font-serif text-3xl tracking-tight">Contact</h2>
        </div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {items.map((item) => {
            const Icon = item.icon
            return (
              <div
                key={item.label}
                className="flex flex-col gap-2 rounded-xl border border-border bg-card p-6"
              >
                <Icon className="size-5 text-primary" />
                <p className="text-sm font-medium">{item.label}</p>
                {item.href ? (
                  <a
                    href={item.href}
                    className="text-sm text-muted-foreground transition-colors hover:text-foreground"
                  >
                    {item.value}
                  </a>
                ) : (
                  <p className="text-sm text-muted-foreground">{item.value}</p>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </section>
  )
}
