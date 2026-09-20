// Today's date in the user's local timezone as YYYY-MM-DD (toISOString would give the UTC date).
export function localToday(now: Date = new Date()): string {
  const mm = String(now.getMonth() + 1).padStart(2, '0')
  const dd = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${mm}-${dd}`
}
