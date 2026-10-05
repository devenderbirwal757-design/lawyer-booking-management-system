import { FormSkeleton } from '@/components/shared/skeletons'

export default function AdminLoginLoading() {
  return (
    <div className="flex min-h-[80dvh] items-center justify-center px-4">
      <FormSkeleton fields={3} />
    </div>
  )
}
