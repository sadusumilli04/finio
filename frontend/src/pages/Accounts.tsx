import { useState, type FormEvent } from 'react'
import { api, type Account, type AccountSource, type AccountType } from '../api'
import { deleteAccountPrompt } from '../lib/accountDelete'
import { useFetch } from '../lib/useFetch'

const SOURCE_LABELS: Record<AccountSource, string> = {
  apple_card_csv: 'Apple Card CSV import',
  venmo_csv: 'Venmo CSV import',
  manual: 'Manual entry',
}

export default function Accounts() {
  const accounts = useFetch(api.accounts, [])
  const [name, setName] = useState('')
  const [type, setType] = useState<AccountType>('checking')
  const [source, setSource] = useState<AccountSource>('manual')
  const [error, setError] = useState<string | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (!name.trim()) return setError('Name is required')
    try {
      await api.createAccount({ name: name.trim(), type, source })
      setName('')
      accounts.reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  async function remove(a: Account) {
    if (!window.confirm(deleteAccountPrompt(a.name, a.transaction_count))) return
    setError(null)
    try {
      await api.deleteAccount(a.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      accounts.reload()
    }
  }

  return (
    <section>
      <h1>Accounts</h1>
      {accounts.error && <p className="error">{accounts.error}</p>}
      {!accounts.error && accounts.data === null && <p className="muted">Loading…</p>}
      {accounts.data !== null && accounts.data.length > 0 && (
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Type</th>
            <th>Source</th>
            <th className="num">Transactions</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {accounts.data?.map((a) => (
            <tr key={a.id}>
              <td>{a.name}</td>
              <td>{a.type}</td>
              <td>{SOURCE_LABELS[a.source]}</td>
              <td className="num">{a.transaction_count.toLocaleString('en-US')}</td>
              <td>
                <button type="button" onClick={() => void remove(a)}>
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      )}
      {accounts.data?.length === 0 &&<p className="muted">No accounts yet. Create an account first.</p>}

      <h2>Add account</h2>
      <form onSubmit={submit} className="form-row">
        <input placeholder="Account name" value={name} onChange={(e) => setName(e.target.value)} />
        <select value={type} onChange={(e) => setType(e.target.value as AccountType)}>
          <option value="credit_card">Credit card</option>
          <option value="checking">Checking</option>
          <option value="savings">Savings</option>
          <option value="other">Other</option>
        </select>
        <select value={source} onChange={(e) => setSource(e.target.value as AccountSource)}>
          <option value="apple_card_csv">Apple Card CSV import</option>
          <option value="venmo_csv">Venmo CSV import</option>
          <option value="manual">Manual entry</option>
        </select>
        <button type="submit">Add</button>
      </form>
      {error && <p className="error">{error}</p>}
    </section>
  )
}
