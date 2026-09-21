import { describe, expect, it } from 'vitest'
import type { Transaction } from '../api'
import { mergePinned } from './pinnedRows'

function txn(id: number, category = 'Other'): Transaction {
  return {
    id,
    account_id: 1,
    account_name: 'Apple Card',
    transaction_date: '2026-09-01',
    posted_date: null,
    amount: 1000,
    type: 'purchase',
    merchant: `Merchant ${id}`,
    description: `Merchant ${id}`,
    cardholder: null,
    category_id: 1,
    category,
    category_source: 'source_default',
    origin: 'import',
  }
}

describe('mergePinned', () => {
  it('returns the fetched rows untouched when nothing is pinned', () => {
    const items = [txn(1), txn(2)]
    expect(mergePinned(items, [])).toEqual({ rows: items, recentIds: new Set(), hiddenCount: 0 })
  })

  it('keeps a pinned row that the current filters no longer return, at the top', () => {
    const items = [txn(2), txn(3)]
    const pinned = [txn(1, 'Insurance')]
    const result = mergePinned(items, pinned)
    expect(result.rows.map((r) => r.id)).toEqual([1, 2, 3])
    expect(result.rows[0].category).toBe('Insurance')
    expect(result.recentIds).toEqual(new Set([1]))
    expect(result.hiddenCount).toBe(1)
  })

  it('prefers the freshly fetched copy of a pinned row that is still returned, without duplicating it', () => {
    const items = [txn(1, 'Insurance'), txn(2)]
    const pinned = [txn(1, 'Stale')]
    const result = mergePinned(items, pinned)
    expect(result.rows.map((r) => r.id)).toEqual([1, 2])
    expect(result.rows[0].category).toBe('Insurance')
    expect(result.recentIds).toEqual(new Set([1]))
    expect(result.hiddenCount).toBe(0)
  })

  it('keeps several pinned rows in the order given (most recent first)', () => {
    const result = mergePinned([txn(5)], [txn(3), txn(4)])
    expect(result.rows.map((r) => r.id)).toEqual([3, 4, 5])
    expect(result.hiddenCount).toBe(2)
  })
})
