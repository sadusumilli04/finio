import { useState } from 'react'
import { api, type Transaction, type VenmoPayment } from '../api'
import { shortDate } from '../lib/date'
import { formatCents } from '../lib/money'
import { useFetch } from '../lib/useFetch'
import { linkSummary, runLinkAction, wouldExceed } from '../lib/venmoLinks'

type Props = { transaction: Transaction; onDone: (updated: Transaction) => void; onCancel: () => void }

export default function VenmoLinkPanel({ transaction: t, onDone, onCancel }: Props) {
  const links = useFetch(() => api.venmoLinks(t.id), [t.id])
  const candidates = useFetch(() => api.venmoCandidates(t.id), [t.id])
  const [actionError, setActionError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)

  const reimbursed = links.data?.map((p) => p.amount) ?? []
  const loading = links.data === null || candidates.data === null
  const loadError = links.error ?? candidates.error
  const busy = busyId !== null

  function reloadLists() {
    links.reload()
    candidates.reload()
  }

  async function link(payment: VenmoPayment) {
    setActionError(null)
    setBusyId(payment.id)
    await runLinkAction(() => api.linkVenmo(t.id, payment.id), {
      onSuccess: (updated) => {
        onDone(updated)
        reloadLists()
      },
      onError: setActionError,
      reload: reloadLists,
    })
    setBusyId(null)
  }

  async function unlink(payment: VenmoPayment) {
    setActionError(null)
    setBusyId(payment.id)
    await runLinkAction(() => api.unlinkVenmo(t.id, payment.id), {
      onSuccess: (updated) => {
        onDone(updated)
        reloadLists()
      },
      onError: setActionError,
      reload: reloadLists,
    })
    setBusyId(null)
  }

  return (
    <div className="panel venmo-panel">
      <div className="venmo-head">
        <h2>Link Venmo payments to “{t.merchant}”</h2>
        <span className="muted">Charge: {formatCents(t.amount)}</span>
      </div>
      {t.share_source === 'manual' && <p className="muted small">Linking replaces your manual split.</p>}

      {loadError && <p className="error">{loadError}</p>}
      {loading && !loadError && <p className="muted">Loading…</p>}

      {!loading && (
        <>
          {links.data!.length > 0 && (
            <ul className="venmo-list">
              {links.data!.map((p) => (
                <li key={p.id}>
                  <span className="venmo-item-info">
                    <span className="venmo-item-date">{shortDate(p.date)}</span>
                    <span className="venmo-item-who">{p.merchant}</span>
                    <span className="venmo-item-note muted">{p.description}</span>
                  </span>
                  <span className="venmo-item-amount">{formatCents(p.amount)}</span>
                  <button type="button" disabled={busy} onClick={() => void unlink(p)}>
                    Unlink
                  </button>
                </li>
              ))}
            </ul>
          )}

          <p className="venmo-summary">{linkSummary(t.amount, reimbursed)}</p>

          <h3>Candidates</h3>
          {candidates.data!.length === 0 ? (
            <p className="muted small">No unlinked Venmo payments in range.</p>
          ) : (
            <ul className="venmo-list">
              {candidates.data!.map((p) => {
                const exceeds = wouldExceed(t.amount, reimbursed, p.amount)
                return (
                  <li key={p.id}>
                    <span className="venmo-item-info">
                      <span className="venmo-item-date">{shortDate(p.date)}</span>
                      <span className="venmo-item-who">{p.merchant}</span>
                      <span className="venmo-item-note muted">{p.description}</span>
                    </span>
                    <span className="venmo-item-amount">{formatCents(p.amount)}</span>
                    {exceeds && <span className="muted small venmo-exceeds">Exceeds the charge</span>}
                    <button type="button" disabled={exceeds || busy} onClick={() => void link(p)}>
                      Link
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </>
      )}

      {actionError && <p className="error">{actionError}</p>}
      <div className="form-row">
        <button type="button" onClick={onCancel}>
          Close
        </button>
      </div>
    </div>
  )
}
