import { describe, expect, it } from 'vitest'
import { evenShare, parseShareToCents, validateSplit } from './split'

describe('parseShareToCents', () => {
  it('parses plain and formatted amounts', () => {
    expect(parseShareToCents('30')).toBe(3000)
    expect(parseShareToCents('30.5')).toBe(3050)
    expect(parseShareToCents('$1,234.56')).toBe(123456)
    expect(parseShareToCents(' 0.07 ')).toBe(7)
  })
  it('accepts zero, unlike the general amount parser', () => {
    expect(parseShareToCents('0')).toBe(0)
    expect(parseShareToCents('0.00')).toBe(0)
  })
  it('rejects invalid input', () => {
    expect(parseShareToCents('')).toBeNull()
    expect(parseShareToCents('abc')).toBeNull()
    expect(parseShareToCents('-5')).toBeNull()
    expect(parseShareToCents('1.234')).toBeNull()
  })
})

describe('evenShare', () => {
  it('divides the charge and rounds to the nearest cent', () => {
    expect(evenShare(12000, 4)).toBe(3000)
    expect(evenShare(10000, 3)).toBe(3333)
    expect(evenShare(10001, 2)).toBe(5001)
  })
  it('needs a whole number of at least two people', () => {
    expect(evenShare(12000, 1)).toBeNull()
    expect(evenShare(12000, 0)).toBeNull()
    expect(evenShare(12000, 2.5)).toBeNull()
    expect(evenShare(12000, Number.NaN)).toBeNull()
  })
})

describe('validateSplit', () => {
  it('accepts an amount up to and including the charge, and zero', () => {
    expect(validateSplit('30.00', 12000)).toEqual({ ok: true, cents: 3000 })
    expect(validateSplit('120', 12000)).toEqual({ ok: true, cents: 12000 })
    expect(validateSplit('0', 12000)).toEqual({ ok: true, cents: 0 })
  })
  it('rejects blank, invalid, and too-large values with a clear message', () => {
    expect(validateSplit('', 12000)).toEqual({ ok: false, error: 'Enter your share, like 30.00' })
    expect(validateSplit('abc', 12000)).toEqual({ ok: false, error: 'Enter your share, like 30.00' })
    expect(validateSplit('120.01', 12000)).toEqual({
      ok: false,
      error: "Your share can't be more than the charge ($120.00)",
    })
  })
})
