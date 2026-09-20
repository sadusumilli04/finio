import { describe, expect, it } from 'vitest'
import { localToday } from './date'

describe('localToday', () => {
  it('formats a local date with zero padding', () => {
    expect(localToday(new Date(2026, 8, 5))).toBe('2026-09-05')
  })
  it('stays on the local day late in the evening', () => {
    expect(localToday(new Date(2026, 11, 31, 23, 30))).toBe('2026-12-31')
  })
})
