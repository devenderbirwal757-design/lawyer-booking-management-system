import { CheckIcon } from 'lucide-react'

import { cn } from 'cn'

const STEPS = ['Service', 'Date & time', 'Your details', 'Payment', 'Confirmed']

export function Stepper({
  current,
  onNavigate,
}: {
  current: number
  onNavigate?: (index: number) => void
}) {
  return (
    <ol className="flex items-center gap-1 overflow-x-auto text-xs sm:gap-2 sm:text-sm">
      {STEPS.map((label, index) => {
        const done = index < current
        const active = index === current
        return (
          <li key={label} className="flex items-center gap-1 sm:gap-2">
            {index > 0 && (
              <span
                aria-hidden
                className={cn(
                  'h-px w-3 bg-border sm:w-6',
                  done && 'bg-primary'
                )}
              />
            )}
            <button
              type="button"
              disabled={index > current}
              aria-current={active ? 'step' : undefined}
              onClick={() => onNavigate?.(index)}
              className={cn(
                'flex items-center gap-1.5 rounded-full border px-2 py-1 transition-colors sm:px-2.5',
                active && 'border-primary bg-primary text-primary-foreground',
                done && 'border-primary/40 text-primary hover:bg-primary/5',
                !active && !done && 'border-border text-muted-foreground'
              )}
            >
              <span
                aria-hidden
                className={cn(
                  'flex size-4 items-center justify-center rounded-full text-[10px]',
                  active && 'bg-primary-foreground text-primary',
                  done && 'bg-primary text-primary-foreground'
                )}
              >
                {done ? <CheckIcon className="size-3" /> : index + 1}
              </span>
              <span className="hidden sm:inline">{label}</span>
            </button>
          </li>
        )
      })}
    </ol>
  )
}
