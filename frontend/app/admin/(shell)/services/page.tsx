'use client'

import { PencilIcon, PlusIcon, Trash2Icon } from 'lucide-react'
import { QueryError } from '@/components/shared/query-error'
import { useState } from 'react'
import { toast } from 'sonner'

import { ServiceDrawer } from '@/components/admin/service-drawer'
import { DataTable } from '@/components/shared/data-table'
import { PageHeader } from '@/components/shared/page-header'
import { Price } from '@/components/shared/price'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/shared/confirm-dialog'
import { toApiError } from '@/lib/api/error'

import { useAdminServices, useDeleteService } from '@/features/admin/api'
import type { AdminService } from '@/features/admin/schema'

export default function AdminServicesPage() {
  const services = useAdminServices()
  const remove = useDeleteService()

  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editing, setEditing] = useState<AdminService | null>(null)
  const [deleting, setDeleting] = useState<AdminService | null>(null)

  const openCreate = () => {
    setEditing(null)
    setDrawerOpen(true)
  }

  const openEdit = (service: AdminService) => {
    setEditing(service)
    setDrawerOpen(true)
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Services"
        description="What clients can book, how long it takes, and what it costs."
        actions={
          <Button onClick={openCreate}>
            <PlusIcon className="size-4" /> New service
          </Button>
        }
      />

      {services.isError ? (
        <QueryError
          error={services.error}
          onRetry={() => void services.refetch()}
          isRetrying={false}
        />
      ) : (
        <DataTable
          data={services.data ?? []}
          keyFor={(row) => row.id}
          loading={services.isLoading}
          emptyTitle="No services yet"
          emptyDescription="Add your first consultation type to open bookings."
          columns={[
            {
              header: 'Service',
              cell: (row) => (
                <div className="flex flex-col">
                  <span className="font-medium">{row.name}</span>
                  {row.description ? (
                    <span className="text-xs text-muted-foreground">
                      {row.description}
                    </span>
                  ) : null}
                </div>
              ),
            },
            {
              header: 'Duration',
              cell: (row) =>
                row.duration_minutes ? `${row.duration_minutes} min` : '—',
            },
            {
              header: 'Price',
              cell: (row) =>
                row.price != null ? <Price amount={row.price} /> : '—',
            },
            {
              header: 'Status',
              cell: (row) => (
                <Badge variant={row.is_active ? 'default' : 'secondary'}>
                  {row.is_active ? 'Active' : 'Inactive'}
                </Badge>
              ),
            },
            {
              header: <span className="sr-only">Actions</span>,
              cell: (row) => (
                <div className="flex justify-end gap-1">
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Edit ${row.name}`}
                    onClick={() => openEdit(row)}
                  >
                    <PencilIcon className="size-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Delete ${row.name}`}
                    onClick={() => setDeleting(row)}
                  >
                    <Trash2Icon className="size-4" />
                  </Button>
                </div>
              ),
              className: 'w-20 text-right',
            },
          ]}
        />
      )}

      <ServiceDrawer
        service={editing}
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
      />

      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => {
          if (!open) setDeleting(null)
        }}
        title={`Delete ${deleting?.name ?? 'service'}?`}
        description="Services with existing appointments are archived instead of deleted."
        confirmLabel="Delete"
        destructive
        loading={remove.isPending}
        onConfirm={() => {
          if (!deleting) return
          remove.mutate(deleting.id, {
            onSuccess: () => {
              toast.success('Service deleted')
              setDeleting(null)
            },
            onError: (error) => toast.error(toApiError(error).message),
          })
        }}
      />
    </div>
  )
}
