import { formatCents } from './money'

const ENTER_SHARE = 'Enter your share, like 30.00'

// Like parseAmountToCents, but zero is a valid share (someone else covered the whole charge).
export function parseShareToCents(input: string): number | null {
  const cleaned = input.trim().replace(/[$,\s]/g, '')
  if (!/^\d+(\.\d{1,2})?$/.test(cleaned)) return null
  const [dollars, fraction = ''] = cleaned.split('.')
  return parseInt(dollars, 10) * 100 + parseInt(fraction.padEnd(2, '0') || '0', 10)
}

export function evenShare(chargeCents: number, people: number): number | null {
  if (!Number.isInteger(people) || people < 2) return null
  return Math.round(chargeCents / people)
}

export function validateSplit(
  text: string,
  chargeCents: number,
): { ok: true; cents: number } | { ok: false; error: string } {
  const cents = parseShareToCents(text)
  if (cents === null) return { ok: false, error: ENTER_SHARE }
  if (cents > chargeCents) {
    return { ok: false, error: `Your share can't be more than the charge (${formatCents(chargeCents)})` }
  }
  return { ok: true, cents }
}
