import { Skeleton } from '@/components/ui/skeleton'

export function KpiCard({
  label,
  value,
  hint,
  icon,
  loading,
}: {
  label: string
  value: React.ReactNode
  hint?: string
  icon?: React.ReactNode
  loading?: boolean
}) {
  return (
    <div className="flex flex-col gap-2 rounded-2xl border border-border bg-card p-4">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm text-muted-foreground">{label}</span>
        {icon ? <span className="text-muted-foreground">{icon}</span> : null}
      </div>
      {loading ? (
        <Skeleton className="h-8 w-24" />
      ) : (
        <div className="flex items-baseline gap-2">
          <span className="text-2xl font-semibold tracking-tight">{value}</span>
          {hint ? (
            <span className="text-xs text-muted-foreground">{hint}</span>
          ) : null}
        </div>
      )}
    </div>
  )
}
