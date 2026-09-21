import { describe, expect, it } from 'vitest'
import { localToday, shortDate } from './date'

describe('localToday', () => {
  it('formats a local date with zero padding', () => {
    expect(localToday(new Date(2026, 8, 5))).toBe('2026-09-05')
  })
  it('stays on the local day late in the evening', () => {
    expect(localToday(new Date(2026, 11, 31, 23, 30))).toBe('2026-12-31')
  })
})

describe('shortDate', () => {
  it('formats an ISO date as "Mon D, YYYY" without shifting the day', () => {
    expect(shortDate('2026-09-05')).toBe('Sep 5, 2026')
    expect(shortDate('2026-12-31')).toBe('Dec 31, 2026')
    expect(shortDate('2026-01-01')).toBe('Jan 1, 2026')
  })
})
