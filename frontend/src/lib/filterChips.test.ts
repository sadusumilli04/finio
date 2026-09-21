import { describe, expect, it } from 'vitest'
import { buildChips } from './filterChips'

const names: Record<string, string> = { '2': 'Apple Card' }
const opts = (minText = '', maxText = '') => ({ accountName: (id: string) => names[id], minText, maxText })

describe('buildChips', () => {
  it('returns nothing when no filter is set', () => {
    expect(buildChips({}, opts())).toEqual([])
  })

  it('describes a full date range, and open-ended ranges', () => {
    expect(buildChips({ date_from: '2026-09-01', date_to: '2026-09-30' }, opts())).toEqual([
      { key: 'date', label: 'Sep 1, 2026 – Sep 30, 2026' },
    ])
    expect(buildChips({ date_from: '2026-09-01' }, opts())).toEqual([{ key: 'date', label: 'From Sep 1, 2026' }])
    expect(buildChips({ date_to: '2026-12-31' }, opts())).toEqual([{ key: 'date', label: 'Until Dec 31, 2026' }])
  })

  it('shows the cardholder and the account name, falling back to the id', () => {
    expect(buildChips({ cardholder: 'Siri' }, opts())).toEqual([{ key: 'cardholder', label: 'Cardholder: Siri' }])
    expect(buildChips({ account_id: '2' }, opts())).toEqual([{ key: 'account', label: 'Account: Apple Card' }])
    expect(buildChips({ account_id: '9' }, opts())).toEqual([{ key: 'account', label: 'Account: 9' }])
  })

  it('describes amount bounds from what the user typed', () => {
    expect(buildChips({}, opts('10', '50'))).toEqual([{ key: 'amount', label: '$10 – $50' }])
    expect(buildChips({}, opts(' 10 ', ''))).toEqual([{ key: 'amount', label: 'Over $10' }])
    expect(buildChips({}, opts('', '50'))).toEqual([{ key: 'amount', label: 'Under $50' }])
  })

  it('keeps a stable order: date, cardholder, account, amount', () => {
    const chips = buildChips({ account_id: '2', cardholder: 'Siri', date_from: '2026-09-01' }, opts('5', ''))
    expect(chips.map((c) => c.key)).toEqual(['date', 'cardholder', 'account', 'amount'])
  })
})
