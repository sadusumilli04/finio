import { useState, type FormEvent } from 'react'
import { api, type AccountSource, type AccountType } from '../api'
import { useFetch } from '../lib/useFetch'

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
          </tr>
        </thead>
        <tbody>
          {accounts.data?.map((a) => (
            <tr key={a.id}>
              <td>{a.name}</td>
              <td>{a.type}</td>
              <td>{a.source === 'apple_card_csv' ? 'Apple Card CSV import' : 'Manual entry'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      )}
      {accounts.data?.length === 0 &&<p className="muted">No accounts yet. Create your Apple Card account first.</p>}

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
          <option value="manual">Manual entry</option>
        </select>
        <button type="submit">Add</button>
      </form>
      {error && <p className="error">{error}</p>}
    </section>
  )
}
