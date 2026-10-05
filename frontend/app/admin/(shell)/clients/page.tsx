'use client'

import { format } from 'date-fns'
import { QueryError } from '@/components/shared/query-error'
import { SearchIcon } from 'lucide-react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useEffect, useState } from 'react'

import { Pagination } from '@/components/admin/pagination'
import { DataTable } from '@/components/shared/data-table'
import { PageHeader } from '@/components/shared/page-header'
import { Input } from '@/components/ui/input'
import { useDebounce } from '@/lib/hooks/use-debounce'

import { useAdminCustomers } from '@/features/admin/api'

export default function AdminClientsPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const q = searchParams.get('q') ?? ''
  const page = searchParams.get('page')
    ? Number(searchParams.get('page'))
    : undefined

  const [search, setSearch] = useState(q)
  const debounced = useDebounce(search)

  const customers = useAdminCustomers({ q: q || undefined, page })

  useEffect(() => {
    const current = searchParams.get('q') ?? ''
    if (debounced === current) return
    const params = new URLSearchParams(searchParams.toString())
    if (debounced) {
      params.set('q', debounced)
    } else {
      params.delete('q')
    }
    params.delete('page')
    const query = params.toString()
    router.replace(query ? `?${query}` : '/admin/clients')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced])

  const setPage = (next: number) => {
    const params = new URLSearchParams(searchParams.toString())
    if (next > 1) {
      params.set('page', String(next))
    } else {
      params.delete('page')
    }
    const query = params.toString()
    router.replace(query ? `?${query}` : '/admin/clients')
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Clients"
        description="Everyone who has booked a consultation."
      />

      <div className="relative w-full max-w-sm">
        <SearchIcon className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by name, phone, or email…"
          className="h-9 pl-8"
          aria-label="Search clients"
        />
      </div>

      {customers.isError ? (
        <QueryError
          error={customers.error}
          onRetry={() => void customers.refetch()}
          isRetrying={false}
        />
      ) : (
        <>
          <DataTable
            data={customers.data?.results ?? []}
            keyFor={(row) => row.id}
            loading={customers.isLoading}
            emptyTitle={q ? 'No clients match your search' : 'No clients yet'}
            emptyDescription={
              q ? 'Try a different name, phone, or email.' : undefined
            }
            columns={[
              {
                header: 'Name',
                cell: (row) => (
                  <Link
                    href={`/admin/clients/${row.id}`}
                    className="font-medium hover:underline"
                  >
                    {row.name ?? '—'}
                  </Link>
                ),
              },
              {
                header: 'Phone',
                cell: (row) => (
                  <span className="text-muted-foreground">
                    {row.phone ?? '—'}
                  </span>
                ),
              },
              {
                header: 'Email',
                cell: (row) => (
                  <span className="text-muted-foreground">
                    {row.email ?? '—'}
                  </span>
                ),
              },
              {
                header: 'Appointments',
                cell: (row) => row.appointment_count ?? '—',
              },
              {
                header: 'Last visit',
                cell: (row) =>
                  row.last_appointment_at ? (
                    format(new Date(row.last_appointment_at), 'd MMM yyyy')
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  ),
              },
            ]}
          />
          <Pagination
            hasPrevious={Boolean(customers.data?.previous)}
            hasNext={Boolean(customers.data?.next)}
            disabled={customers.isFetching}
            onPrevious={() => setPage((page ?? 1) - 1)}
            onNext={() => setPage((page ?? 1) + 1)}
          />
        </>
      )}
    </div>
  )
}
