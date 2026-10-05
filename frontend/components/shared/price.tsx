import { formatMoney } from '@/lib/utils/money'

export function Price({
  amount,
  currency = 'INR',
  className,
}: {
  amount: number
  currency?: string
  className?: string
}) {
  return <span className={className}>{formatMoney(amount, currency)}</span>
}
