import { EmptyState } from '@/components/shared/empty-state'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

export interface DataTableColumn<T> {
  header: React.ReactNode
  cell: (row: T) => React.ReactNode
  className?: string
  headClassName?: string
}

interface DataTableProps<T> {
  data: T[]
  columns: Array<DataTableColumn<T>>
  keyFor: (row: T) => string
  loading?: boolean
  skeletonRows?: number
  emptyTitle: string
  emptyDescription?: string
  onRetry?: () => void
}

export function DataTable<T>({
  data,
  columns,
  keyFor,
  loading,
  skeletonRows = 4,
  emptyTitle,
  emptyDescription,
  onRetry,
}: DataTableProps<T>) {
  if (loading) {
    return (
      <div className="flex flex-col gap-2">
        {Array.from({ length: skeletonRows }).map((_, i) => (
          <Skeleton key={i} className="h-11 w-full rounded-lg" />
        ))}
      </div>
    )
  }

  if (!data.length) {
    return (
      <EmptyState
        title={emptyTitle}
        description={emptyDescription}
        actionLabel={onRetry ? 'Retry' : undefined}
        onAction={onRetry}
      />
    )
  }

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            {columns.map((column, index) => (
              <TableHead key={index} className={column.headClassName}>
                {column.header}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.map((row) => (
            <TableRow key={keyFor(row)}>
              {columns.map((column, index) => (
                <TableCell key={index} className={column.className}>
                  {column.cell(row)}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
