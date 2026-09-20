const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })

export function formatCents(cents: number): string {
  return usd.format(cents / 100)
}

export function parseAmountToCents(input: string): number | null {
  const cleaned = input.trim().replace(/[$,\s]/g, '')
  if (!/^\d+(\.\d{1,2})?$/.test(cleaned)) return null
  const [dollars, fraction = ''] = cleaned.split('.')
  const cents = parseInt(dollars, 10) * 100 + parseInt(fraction.padEnd(2, '0') || '0', 10)
  return cents > 0 ? cents : null
}
