import { describe, expect, it } from 'vitest'
import { changeText, formatPercent, monthLabel, neighborMonth, paceText, rankText, subscriptionTag } from './insights'

describe('monthLabel', () => {
  it('spells out the month', () => expect(monthLabel('2026-09')).toBe('September 2026'))
  it('marks a month in progress', () => expect(monthLabel('2026-09', true)).toBe('September 2026 (in progress)'))
})

describe('neighborMonth', () => {
  const months = ['2026-07', '2026-08', '2026-09']
  it('moves to the previous and the next available month', () => {
    expect(neighborMonth(months, '2026-08', -1)).toBe('2026-07')
    expect(neighborMonth(months, '2026-08', 1)).toBe('2026-09')
  })
  it('stops at the ends', () => {
    expect(neighborMonth(months, '2026-07', -1)).toBeNull()
    expect(neighborMonth(months, '2026-09', 1)).toBeNull()
  })
  it('skips months without spending and copes with an unknown month', () => {
    expect(neighborMonth(['2026-01', '2026-04'], '2026-04', -1)).toBe('2026-01')
    expect(neighborMonth(months, '2025-01', 1)).toBeNull()
  })
})

describe('formatPercent', () => {
  it('signs the number and drops a trailing .0', () => {
    expect(formatPercent(12)).toBe('+12%')
    expect(formatPercent(12.0)).toBe('+12%')
    expect(formatPercent(-8.4)).toBe('-8.4%')
    expect(formatPercent(0)).toBe('0%')
  })
})

describe('changeText', () => {
  it('says up, down or the same, in words', () => {
    expect(changeText(21200, 12, 'Aug 1–20')).toBe('Up $212.00 (+12%) vs Aug 1–20')
    expect(changeText(-5000, -5, 'August')).toBe('Down $50.00 (-5%) vs August')
    expect(changeText(0, 0, 'August')).toBe('Same as August')
  })
  it('leaves the percent out when there is nothing to divide by', () => {
    expect(changeText(5000, null, 'August')).toBe('Up $50.00 vs August')
  })
})

describe('paceText', () => {
  it('shows the pace once there is a projection', () => {
    expect(paceText(20, 30, 185100)).toBe('Day 20 of 30 · on pace for $1,851.00')
  })
  it('shows only the day early in the month', () => expect(paceText(5, 30, null)).toBe('Day 5 of 30'))
})

describe('rankText', () => {
  it('uses ordinals', () => {
    const t = (position: number) => rankText({ position, of: 9 })
    expect([1, 2, 3, 4, 11, 12, 13, 21, 22, 23].map(t)).toEqual([
      '1st highest of 9 months', '2nd highest of 9 months', '3rd highest of 9 months', '4th highest of 9 months',
      '11th highest of 9 months', '12th highest of 9 months', '13th highest of 9 months', '21st highest of 9 months',
      '22nd highest of 9 months', '23rd highest of 9 months',
    ])
  })
})

describe('subscriptionTag', () => {
  it('names every kind', () => {
    expect(['price_up', 'price_down', 'new', 'missing'].map((k) => subscriptionTag(k as never))).toEqual([
      'Price up', 'Price down', 'New', 'Missing',
    ])
  })
})
