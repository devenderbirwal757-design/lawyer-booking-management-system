import { siteConfig } from '@/lib/constants/site'

export function Faq() {
  return (
    <section id="faq" className="mx-auto w-full max-w-3xl px-4 py-16">
      <div className="mb-8 flex flex-col gap-2">
        <p className="text-sm font-medium text-primary">Good to know</p>
        <h2 className="font-serif text-3xl tracking-tight">
          Frequently asked questions
        </h2>
      </div>

      <div className="flex flex-col gap-3">
        {siteConfig.faq.map((item) => (
          <details
            key={item.question}
            className="group rounded-xl border border-border bg-card px-5 py-4"
          >
            <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-sm font-medium [&::-webkit-details-marker]:hidden">
              {item.question}
              <span
                aria-hidden
                className="text-muted-foreground transition-transform group-open:rotate-45"
              >
                +
              </span>
            </summary>
            <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
              {item.answer}
            </p>
          </details>
        ))}
      </div>
    </section>
  )
}
