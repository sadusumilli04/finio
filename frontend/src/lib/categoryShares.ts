import type { CategoryTotal } from '../api'

export type CategoryShare = CategoryTotal & { percent: number }

/** Adds each category's share of total spending as a percent rounded to one decimal; order is preserved. */
export function withShares(data: CategoryTotal[]): CategoryShare[] {
  const sum = data.reduce((acc, c) => acc + c.total, 0)
  return data.map((c) => ({ ...c, percent: sum === 0 ? 0 : Math.round((c.total / sum) * 1000) / 10 }))
}
