import { parseAmountToCents } from './money'

type Values = { accountId: string; date: string; amount: string; merchant: string; categoryId: string }
type Result = { ok: true; amountCents: number } | { ok: false; error: string }

export function validateManualForm(v: Values): Result {
  if (!v.accountId) return { ok: false, error: 'Pick an account' }
  if (!v.date) return { ok: false, error: 'Date is required' }
  const amountCents = parseAmountToCents(v.amount)
  if (amountCents === null) return { ok: false, error: 'Enter an amount greater than 0, like 12.50' }
  if (!v.merchant.trim()) return { ok: false, error: 'Merchant is required' }
  if (!v.categoryId) return { ok: false, error: 'Pick a category' }
  return { ok: true, amountCents }
}
