import { describe, expect, it } from 'vitest'
import { activePreset, DATE_PRESETS, presetRange } from './datePresets'

const sep21 = new Date(2026, 8, 21) // September 21, 2026 (local time)

describe('presetRange', () => {
  it('covers the whole current month', () => {
    expect(presetRange('thisMonth', sep21)).toEqual({ date_from: '2026-09-01', date_to: '2026-09-30' })
  })

  it('covers the whole previous month', () => {
    expect(presetRange('lastMonth', sep21)).toEqual({ date_from: '2026-08-01', date_to: '2026-08-31' })
  })

  it('covers six calendar months ending with the current month', () => {
    expect(presetRange('last6Months', sep21)).toEqual({ date_from: '2026-04-01', date_to: '2026-09-30' })
  })

  it('covers the current calendar year and the previous one', () => {
    expect(presetRange('wholeYear', sep21)).toEqual({ date_from: '2026-01-01', date_to: '2026-12-31' })
    expect(presetRange('lastYear', sep21)).toEqual({ date_from: '2025-01-01', date_to: '2025-12-31' })
  })

  it('rolls back across a year boundary in January', () => {
    const jan15 = new Date(2027, 0, 15)
    expect(presetRange('lastMonth', jan15)).toEqual({ date_from: '2026-12-01', date_to: '2026-12-31' })
    expect(presetRange('last6Months', jan15)).toEqual({ date_from: '2026-08-01', date_to: '2027-01-31' })
  })

  it('knows month lengths, including leap-year February', () => {
    expect(presetRange('lastMonth', new Date(2028, 2, 10))).toEqual({ date_from: '2028-02-01', date_to: '2028-02-29' })
    expect(presetRange('lastMonth', new Date(2027, 2, 10))).toEqual({ date_from: '2027-02-01', date_to: '2027-02-28' })
  })
})

describe('activePreset', () => {
  it('finds the preset whose range exactly matches the filters', () => {
    expect(activePreset({ date_from: '2026-08-01', date_to: '2026-08-31' }, sep21)).toBe('lastMonth')
    expect(activePreset({ date_from: '2025-01-01', date_to: '2025-12-31' }, sep21)).toBe('lastYear')
  })

  it('returns null for custom or partial ranges', () => {
    expect(activePreset({}, sep21)).toBeNull()
    expect(activePreset({ date_from: '2026-08-01' }, sep21)).toBeNull()
    expect(activePreset({ date_from: '2026-08-02', date_to: '2026-08-31' }, sep21)).toBeNull()
  })
})

describe('DATE_PRESETS', () => {
  it('lists the options in the order shown to the user', () => {
    expect(DATE_PRESETS.map((p) => p.label)).toEqual(['This month', 'Last month', 'Last 6 months', 'Whole year', 'Last year'])
  })
})
