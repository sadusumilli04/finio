import { describe, expect, it } from 'vitest'
import type { CategoryTotal } from '../api'
import { withShares } from './categoryShares'

const row = (id: number, category: string, total: number): CategoryTotal => ({ category_id: id, category, total, count: 1 })

describe('withShares', () => {
  it('adds each category\'s percent of total spending, rounded to one decimal, keeping order', () => {
    const result = withShares([row(1, 'Grocery', 7500), row(2, 'Restaurants', 2000), row(3, 'Other', 500)])
    expect(result.map((r) => [r.category, r.percent])).toEqual([
      ['Grocery', 75],
      ['Restaurants', 20],
      ['Other', 5],
    ])
  })

  it('rounds awkward shares', () => {
    const result = withShares([row(1, 'A', 1), row(2, 'B', 2)])
    expect(result.map((r) => r.percent)).toEqual([33.3, 66.7])
  })

  it('keeps the original fields', () => {
    const [first] = withShares([row(4, 'Insurance', 141276)])
    expect(first).toMatchObject({ category_id: 4, category: 'Insurance', total: 141276, count: 1, percent: 100 })
  })

  it('handles no spending without dividing by zero', () => {
    expect(withShares([])).toEqual([])
    expect(withShares([row(1, 'A', 0)]).map((r) => r.percent)).toEqual([0])
  })
})
