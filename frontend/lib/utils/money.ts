const inrFormatter = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
})

const fallbackFormatter = (amount: number, currency: string) =>
  new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(amount)

export function formatMoney(amount: number, currency = 'INR'): string {
  if (!Number.isFinite(amount)) {
    throw new TypeError('formatMoney expects a finite number')
  }
  if (currency.toUpperCase() === 'INR') {
    return inrFormatter.format(amount)
  }
  return fallbackFormatter(amount, currency.toUpperCase())
}

export function formatDuration(durationMinutes: number): string {
  const hours = Math.floor(durationMinutes / 60)
  const minutes = durationMinutes % 60

  if (hours === 0) {
    return `${minutes} min`
  }
  if (minutes === 0) {
    return `${hours} hr`
  }
  return `${hours} hr ${minutes} min`
}
