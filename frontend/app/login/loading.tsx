import { FormSkeleton } from '@/components/shared/skeletons'

export default function LoginLoading() {
  return (
    <div className="flex min-h-[70dvh] items-center justify-center px-4">
      <FormSkeleton />
    </div>
  )
}
