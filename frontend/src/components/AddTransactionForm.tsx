import { useState, type FormEvent } from 'react'
import { api, type Direction, type Transaction } from '../api'
import { localToday } from '../lib/date'
import { validateManualForm } from '../lib/formValidation'
import { useFetch } from '../lib/useFetch'

type Props = { initial?: Transaction; onDone: () => void; onCancel: () => void }

const LAST_ACCOUNT = 'finio.lastAccount'
const LAST_DATE = 'finio.lastDate'

function remembered(key: string): string {
  try {
    return localStorage.getItem(key) ?? ''
  } catch {
    return ''
  }
}
function remember(key: string, value: string) {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* storage unavailable; the form still works */
  }
}

function directionOf(t: Transaction): Direction {
  return t.type === 'income' ? 'income' : t.type === 'refund' ? 'refund' : 'expense'
}

export default function AddTransactionForm({ initial, onDone, onCancel }: Props) {
  const accounts = useFetch(api.accounts, [])
  const categories = useFetch(api.categories, [])
  const merchants = useFetch(api.merchants, [])

  const [accountId, setAccountId] = useState(initial ? String(initial.account_id) : remembered(LAST_ACCOUNT))
  const [date, setDate] = useState(initial?.transaction_date ?? (remembered(LAST_DATE) || localToday()))
  const [amount, setAmount] = useState(initial ? (Math.abs(initial.amount) / 100).toFixed(2) : '')
  const [direction, setDirection] = useState<Direction>(initial ? directionOf(initial) : 'expense')
  const [merchant, setMerchant] = useState(initial?.merchant ?? '')
  const [description, setDescription] = useState(initial && initial.description !== initial.merchant ? initial.description : '')
  const [cardholder, setCardholder] = useState(initial?.cardholder ?? '')
  const [categoryId, setCategoryId] = useState(initial ? String(initial.category_id) : '')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // The remembered account may have been deleted since it was last used: only accept ids that still exist.
  const selectedAccountId =
    initial || accounts.data?.some((a) => String(a.id) === accountId) ? accountId : ''

  async function submit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    const check = validateManualForm({ accountId: selectedAccountId, date, amount, merchant, categoryId })
    if (!check.ok) return setError(check.error)
    setBusy(true)
    try {
      const shared = {
        date,
        amount: check.amountCents,
        direction,
        merchant: merchant.trim(),
        description: description.trim() || null,
        cardholder: cardholder.trim() || null,
        category_id: Number(categoryId),
      }
      if (initial) await api.updateTransaction(initial.id, shared)
      else await api.createTransaction({ account_id: Number(selectedAccountId), ...shared })
      remember(LAST_ACCOUNT, selectedAccountId)
      remember(LAST_DATE, date)
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="panel" onSubmit={submit}>
      <h2>{initial ? 'Edit transaction' : 'Add transaction'}</h2>
      <div className="form-grid">
        <label>
          Account
          <select value={selectedAccountId} onChange={(e) => setAccountId(e.target.value)} disabled={!!initial}>
            <option value="">Select…</option>
            {accounts.data?.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Date
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <label>
          Amount
          <input inputMode="decimal" placeholder="12.50" value={amount} onChange={(e) => setAmount(e.target.value)} />
        </label>
        <label>
          Type
          <select value={direction} onChange={(e) => setDirection(e.target.value as Direction)}>
            <option value="expense">Expense</option>
            <option value="income">Income</option>
            <option value="refund">Refund</option>
          </select>
        </label>
        <label>
          Merchant
          <input list="merchant-options" value={merchant} onChange={(e) => setMerchant(e.target.value)} />
          <datalist id="merchant-options">
            {merchants.data?.map((m) => (
              <option key={m} value={m} />
            ))}
          </datalist>
        </label>
        <label>
          Category
          <select value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
            <option value="">Select…</option>
            {categories.data?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Description (optional)
          <input value={description} onChange={(e) => setDescription(e.target.value)} />
        </label>
        <label>
          Cardholder (optional)
          <input value={cardholder} onChange={(e) => setCardholder(e.target.value)} />
        </label>
      </div>
      {error && <p className="error">{error}</p>}
      <div className="form-row">
        <button type="submit" disabled={busy}>
          {initial ? 'Save' : 'Add'}
        </button>
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  )
}
