import { describe, expect, it } from 'vitest'
import { validateManualForm } from './formValidation'

const good = { accountId: '1', date: '2026-09-10', amount: '12.50', merchant: 'Cafe', categoryId: '3' }

describe('validateManualForm', () => {
  it('accepts a complete form and returns cents', () => {
    expect(validateManualForm(good)).toEqual({ ok: true, amountCents: 1250 })
  })
  it('requires each field', () => {
    expect(validateManualForm({ ...good, accountId: '' })).toEqual({ ok: false, error: 'Pick an account' })
    expect(validateManualForm({ ...good, date: '' })).toEqual({ ok: false, error: 'Date is required' })
    expect(validateManualForm({ ...good, amount: 'x' })).toEqual({
      ok: false,
      error: 'Enter an amount greater than 0, like 12.50',
    })
    expect(validateManualForm({ ...good, merchant: '   ' })).toEqual({ ok: false, error: 'Merchant is required' })
    expect(validateManualForm({ ...good, categoryId: '' })).toEqual({ ok: false, error: 'Pick a category' })
  })
})
