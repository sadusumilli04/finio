import type { Filters } from '../api'
import { localToday } from './date'

export type PresetKey = 'thisMonth' | 'lastMonth' | 'last6Months' | 'wholeYear' | 'lastYear'

export const DATE_PRESETS: { key: PresetKey; label: string }[] = [
  { key: 'thisMonth', label: 'This month' },
  { key: 'lastMonth', label: 'Last month' },
  { key: 'last6Months', label: 'Last 6 months' },
  { key: 'wholeYear', label: 'Whole year' },
  { key: 'lastYear', label: 'Last year' },
]

type Range = { date_from: string; date_to: string }

// The Date constructor rolls months over for us: month -1 is December of the previous year, and day 0 of the
// next month is the last day of this one (which also handles February and leap years).
const firstOfMonth = (year: number, month: number) => localToday(new Date(year, month, 1))
const lastOfMonth = (year: number, month: number) => localToday(new Date(year, month + 1, 0))

/**
 * The From/To range for a preset, relative to `today`. Ranges are whole calendar months or years:
 * "Last 6 months" is the current month plus the five before it, and "Whole year" is the current calendar year.
 */
export function presetRange(key: PresetKey, today: Date = new Date()): Range {
  const year = today.getFullYear()
  const month = today.getMonth()
  switch (key) {
    case 'thisMonth':
      return { date_from: firstOfMonth(year, month), date_to: lastOfMonth(year, month) }
    case 'lastMonth':
      return { date_from: firstOfMonth(year, month - 1), date_to: lastOfMonth(year, month - 1) }
    case 'last6Months':
      return { date_from: firstOfMonth(year, month - 5), date_to: lastOfMonth(year, month) }
    case 'wholeYear':
      return { date_from: firstOfMonth(year, 0), date_to: lastOfMonth(year, 11) }
    case 'lastYear':
      return { date_from: firstOfMonth(year - 1, 0), date_to: lastOfMonth(year - 1, 11) }
  }
}

/** The preset whose range exactly matches the current From/To filters, or null for a custom or partial range. */
export function activePreset(filters: Filters, today: Date = new Date()): PresetKey | null {
  if (!filters.date_from || !filters.date_to) return null
  const match = DATE_PRESETS.find((p) => {
    const range = presetRange(p.key, today)
    return range.date_from === filters.date_from && range.date_to === filters.date_to
  })
  return match?.key ?? null
}
