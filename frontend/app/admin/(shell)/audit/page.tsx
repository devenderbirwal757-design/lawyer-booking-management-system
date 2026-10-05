'use client'

import { format } from 'date-fns'
import { QueryError } from '@/components/shared/query-error'
import { useState } from 'react'

import { useUrlFilters } from '@/lib/hooks/use-url-filters'

import { AuditDiff } from '@/components/admin/audit-diff'
import { DataTable } from '@/components/shared/data-table'
import { PageHeader } from '@/components/shared/page-header'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'

import { useAdminAuditLogs } from '@/features/admin/api'

const ENTITY_TYPES = [
  'appointment',
  'payment',
  'refund',
  'service',
  'customer',
  'settings',
]

export default function AdminAuditPage() {
  const { values, set } = useUrlFilters({ entity_type: '', entity_id: '' })
  const entityType = values.entity_type
  const entityId = values.entity_id

  const [selected, setSelected] = useState<string | null>(null)

  const logs = useAdminAuditLogs({
    entity_type: entityType || undefined,
    entity_id: entityId || undefined,
  })

  const selectedLog = (logs.data?.results ?? []).find(
    (entry) => entry.id === selected
  )

  const setFilter = (key: string, value: string) => set(key, value)

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Audit log" description="Who changed what, and when." />

      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1.5">
          <label className="text-sm font-medium" htmlFor="audit-entity-type">
            Entity
          </label>
          <select
            id="audit-entity-type"
            value={entityType}
            onChange={(e) => setFilter('entity_type', e.target.value)}
            className="h-9 rounded-md border border-input bg-background px-3 text-sm"
          >
            <option value="">All</option>
            {ENTITY_TYPES.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1.5">
          <label className="text-sm font-medium" htmlFor="audit-entity-id">
            Entity ID
          </label>
          <Input
            id="audit-entity-id"
            value={entityId}
            onChange={(e) => setFilter('entity_id', e.target.value)}
            className="h-9 w-56"
          />
        </div>
      </div>

      {logs.isError ? (
        <QueryError
          error={logs.error}
          onRetry={() => void logs.refetch()}
          isRetrying={false}
        />
      ) : (
        <DataTable
          data={logs.data?.results ?? []}
          keyFor={(row) => row.id}
          loading={logs.isLoading}
          emptyTitle="No audit entries"
          emptyDescription="Actions taken in the admin area show up here."
          columns={[
            {
              header: 'When',
              cell: (row) => (
                <span className="whitespace-nowrap">
                  {format(new Date(row.created_at), 'd MMM yyyy, h:mm a')}
                </span>
              ),
            },
            {
              header: 'Action',
              cell: (row) => (
                <span className="font-medium capitalize">
                  {row.action.replace(/_/g, ' ')}
                </span>
              ),
            },
            {
              header: 'Entity',
              cell: (row) => (
                <span className="text-muted-foreground">
                  {row.entity_type ?? '—'}
                  {row.entity_id ? ` · ${row.entity_id.slice(0, 8)}` : ''}
                </span>
              ),
            },
            {
              header: 'Actor',
              cell: (row) => (
                <span className="text-muted-foreground">
                  {row.actor_type ?? 'system'}
                </span>
              ),
            },
            {
              header: <span className="sr-only">Diff</span>,
              cell: (row) => (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setSelected(row.id)}
                >
                  View changes
                </Button>
              ),
              className: 'text-right',
            },
          ]}
        />
      )}

      {selectedLog ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">
              {selectedLog.action.replace(/_/g, ' ')} ·{' '}
              {format(new Date(selectedLog.created_at), 'd MMM yyyy, h:mm a')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <AuditDiff before={selectedLog.before} after={selectedLog.after} />
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}
