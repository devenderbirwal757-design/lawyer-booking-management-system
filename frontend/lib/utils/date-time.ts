export function secondsUntil(timestamp: string | number | Date): number {
  const target =
    typeof timestamp === 'string'
      ? Date.parse(timestamp)
      : timestamp instanceof Date
        ? timestamp.getTime()
        : timestamp
  if (Number.isNaN(target)) {
    return 0
  }
  return Math.max(0, Math.ceil((target - Date.now()) / 1000))
}
