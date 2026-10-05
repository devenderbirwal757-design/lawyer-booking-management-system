import { siteConfig } from '@/lib/constants/site'

export function PracticeAreas() {
  return (
    <section
      id="practice-areas"
      className="mx-auto w-full max-w-6xl px-4 py-16"
    >
      <div className="mb-8 flex flex-col gap-2">
        <p className="text-sm font-medium text-primary">What I handle</p>
        <h2 className="font-serif text-3xl tracking-tight">Practice areas</h2>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {siteConfig.practiceAreas.map((area) => (
          <div
            key={area.title}
            className="flex flex-col gap-2 rounded-xl border border-border bg-card p-6 transition-colors hover:border-ring"
          >
            <h3 className="font-serif text-lg font-medium">{area.title}</h3>
            <p className="text-sm text-muted-foreground">{area.description}</p>
          </div>
        ))}
      </div>
    </section>
  )
}
