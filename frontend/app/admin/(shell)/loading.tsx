import { PageSkeleton, TableSkeleton } from '@/components/shared/skeletons'

export default function AdminLoading() {
  return (
    <PageSkeleton>
      <TableSkeleton rows={6} columns={5} />
    </PageSkeleton>
  )
}
