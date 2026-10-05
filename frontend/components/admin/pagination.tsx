'use client'

import { ChevronLeftIcon, ChevronRightIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'

export function Pagination({
  hasPrevious,
  hasNext,
  onPrevious,
  onNext,
  disabled,
}: {
  hasPrevious: boolean
  hasNext: boolean
  onPrevious: () => void
  onNext: () => void
  disabled?: boolean
}) {
  if (!hasPrevious && !hasNext) {
    return null
  }
  return (
    <div className="flex items-center justify-end gap-2 pt-3">
      <Button
        variant="outline"
        size="sm"
        disabled={disabled || !hasPrevious}
        onClick={onPrevious}
      >
        <ChevronLeftIcon className="size-4" /> Previous
      </Button>
      <Button
        variant="outline"
        size="sm"
        disabled={disabled || !hasNext}
        onClick={onNext}
      >
        Next <ChevronRightIcon className="size-4" />
      </Button>
    </div>
  )
}
