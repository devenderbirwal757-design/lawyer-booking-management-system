import { WizardSkeleton } from '@/components/shared/skeletons'

export default function BookingLoading() {
  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-10">
      <WizardSkeleton />
    </div>
  )
}
