import { useState, type FormEvent } from 'react'
import { api, type Transaction } from '../api'
import { formatCents } from '../lib/money'
import { evenShare, parseShareToCents, validateSplit } from '../lib/split'

type Props = { transaction: Transaction; onDone: () => void; onCancel: () => void }

export default function SplitPanel({ transaction: t, onDone, onCancel }: Props) {
  const [people, setPeople] = useState('')
  const [share, setShare] = useState(t.my_share === null ? '' : (t.my_share / 100).toFixed(2))
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const typed = parseShareToCents(share)
  const paidForOthers = typed !== null && typed <= t.amount ? t.amount - typed : null

  function fillIn() {
    const cents = evenShare(t.amount, Number(people))
    if (cents === null) return setError('Enter a whole number of people, 2 or more')
    setError(null)
    setShare((cents / 100).toFixed(2))
  }

  async function save(e: FormEvent) {
    e.preventDefault()
    setError(null)
    const check = validateSplit(share, t.amount)
    if (!check.ok) return setError(check.error)
    await send(check.cents)
  }

  async function send(myShare: number | null) {
    setBusy(true)
    try {
      await api.updateTransaction(t.id, { my_share: myShare })
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="panel split-panel" onSubmit={save}>
      <div className="split-head">
        <h2>Split “{t.merchant}”</h2>
        <span className="muted">Charge: {formatCents(t.amount)}</span>
      </div>
      <div className="split-row">
        <label>
          Split evenly among
          <input inputMode="numeric" size={4} placeholder="4" value={people} onChange={(e) => setPeople(e.target.value)} />
          <span>people</span>
        </label>
        <button type="button" onClick={fillIn}>Fill in</button>
      </div>
      <div className="split-row">
        <label>
          My share ($)
          <input inputMode="decimal" size={10} value={share} onChange={(e) => setShare(e.target.value)} autoFocus />
        </label>
        <span className="muted split-others">
          {paidForOthers === null ? '' : `Paid for others: ${formatCents(paidForOthers)}`}
        </span>
      </div>
      {error && <p className="error">{error}</p>}
      <div className="form-row">
        <button type="submit" disabled={busy}>Save split</button>
        <button type="button" onClick={onCancel}>Cancel</button>
        {t.my_share !== null && (
          <button type="button" disabled={busy} onClick={() => void send(null)}>Remove split</button>
        )}
      </div>
    </form>
  )
}
