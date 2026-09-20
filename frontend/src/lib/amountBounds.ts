import { parseAmountToCents } from './money'

const INVALID = 'Enter an amount like 12.50'

export type AmountBounds = {
  min?: number
  max?: number
  minError?: string
  maxError?: string
  rangeError?: string
}

// Blank means no bound; an unparseable value is reported and that bound is dropped.
export function amountBounds(minText: string, maxText: string): AmountBounds {
  const out: AmountBounds = {}
  if (minText.trim()) {
    const cents = parseAmountToCents(minText)
    if (cents === null) out.minError = INVALID
    else out.min = cents
  }
  if (maxText.trim()) {
    const cents = parseAmountToCents(maxText)
    if (cents === null) out.maxError = INVALID
    else out.max = cents
  }
  if (out.min !== undefined && out.max !== undefined && out.min > out.max) {
    return { rangeError: 'Min amount is greater than max amount' }
  }
  return out
}
