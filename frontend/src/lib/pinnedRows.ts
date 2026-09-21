import type { Transaction } from '../api'

/**
 * Rows the user just recategorized are "pinned" so they stay visible even when the active filters
 * (for example a category filter) no longer match them. Fetched rows always win over the pinned
 * copy because they are fresher; pinned rows the fetch did not return are listed first.
 */
export function mergePinned(items: Transaction[], pinned: Transaction[]) {
  const fetchedIds = new Set(items.map((t) => t.id))
  const missing = pinned.filter((t) => !fetchedIds.has(t.id))
  return {
    rows: [...missing, ...items],
    recentIds: new Set(pinned.map((t) => t.id)),
    hiddenCount: missing.length,
  }
}
