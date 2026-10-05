'use client'

import { cn } from 'cn'

function renderValue(value: unknown): string {
  if (value === null || value === undefined) {
    return '—'
  }
  if (typeof value === 'boolean') {
    return value ? 'Yes' : 'No'
  }
  if (typeof value === 'object') {
    return JSON.stringify(value)
  }
  return String(value)
}

function flatEntries(value: unknown): Record<string, unknown> {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>
  }
  return { value }
}

export function AuditDiff({
  before,
  after,
}: {
  before: unknown
  after: unknown
}) {
  const beforeEntries = flatEntries(before)
  const afterEntries = flatEntries(after)
  const keys = Array.from(
    new Set([...Object.keys(beforeEntries), ...Object.keys(afterEntries)])
  ).sort()

  if (!keys.length) {
    return <p className="text-sm text-muted-foreground">No field changes.</p>
  }

  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead className="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
          <tr>
            <th scope="col" className="px-3 py-2 font-medium">
              Field
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              Before
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              After
            </th>
          </tr>
        </thead>
        <tbody>
          {keys.map((key) => {
            const prev = beforeEntries[key]
            const next = afterEntries[key]
            const changed = renderValue(prev) !== renderValue(next)
            return (
              <tr key={key} className="border-t border-border">
                <td className="px-3 py-2 font-medium">{key}</td>
                <td
                  className={cn(
                    'px-3 py-2 text-muted-foreground',
                    changed && 'bg-red-50/60 dark:bg-red-950/20'
                  )}
                >
                  {renderValue(prev)}
                </td>
                <td
                  className={cn(
                    'px-3 py-2',
                    changed
                      ? 'font-medium text-green-700 dark:text-green-300'
                      : 'text-muted-foreground'
                  )}
                >
                  {renderValue(next)}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
