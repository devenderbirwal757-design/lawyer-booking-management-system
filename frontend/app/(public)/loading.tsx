import { CardGridSkeleton, PageSkeleton } from '@/components/shared/skeletons'

export default function PublicLoading() {
  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-16">
      <PageSkeleton>
        <CardGridSkeleton count={6} />
      </PageSkeleton>
    </div>
  )
}
