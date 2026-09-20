import { describe, expect, it } from 'vitest'
import { formatCents, parseAmountToCents } from './money'

describe('formatCents', () => {
  it('formats dollars and cents', () => {
    expect(formatCents(123456)).toBe('$1,234.56')
    expect(formatCents(5)).toBe('$0.05')
    expect(formatCents(0)).toBe('$0.00')
  })
  it('formats negatives', () => {
    expect(formatCents(-500)).toBe('-$5.00')
  })
})

describe('parseAmountToCents', () => {
  it('parses plain and formatted amounts', () => {
    expect(parseAmountToCents('12')).toBe(1200)
    expect(parseAmountToCents('12.5')).toBe(1250)
    expect(parseAmountToCents('$1,234.56')).toBe(123456)
    expect(parseAmountToCents(' 0.07 ')).toBe(7)
  })
  it('rejects invalid input', () => {
    expect(parseAmountToCents('')).toBeNull()
    expect(parseAmountToCents('abc')).toBeNull()
    expect(parseAmountToCents('1.234')).toBeNull()
    expect(parseAmountToCents('-5')).toBeNull()
    expect(parseAmountToCents('0')).toBeNull()
    expect(parseAmountToCents('0.00')).toBeNull()
  })
})
