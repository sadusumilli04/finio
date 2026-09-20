import { useRef, useState, type DragEvent } from 'react'
import { api, type ImportSummary } from '../api'
import { useFetch } from '../lib/useFetch'

export default function Import() {
  const accounts = useFetch(api.accounts, [])
  const importable = accounts.data?.filter((a) => a.source === 'apple_card_csv') ?? []
  const [accountId, setAccountId] = useState<number | null>(null)
  const [summary, setSummary] = useState<ImportSummary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const inFlight = useRef(false)
  const selected = accountId ?? importable[0]?.id ?? null

  async function upload(file: File) {
    if (inFlight.current) return
    if (selected === null) return setError('Create an Apple Card account first')
    inFlight.current = true
    setBusy(true)
    setError(null)
    setSummary(null)
    try {
      setSummary(await api.importFile(selected, file))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      inFlight.current = false
      setBusy(false)
    }
  }

  function onDrop(e: DragEvent) {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    if (file) void upload(file)
  }

  return (
    <section>
      <h1>Import</h1>
      {accounts.error && <p className="error">{accounts.error}</p>}
      {!accounts.error && accounts.data === null && <p className="muted">Loading…</p>}
      {accounts.data !== null && importable.length === 0 && (
        <p className="muted">
          No Apple Card account yet. Add one on the Accounts page with source &ldquo;Apple Card CSV import&rdquo;.
        </p>
      )}
      {importable.length > 0 && (
        <>
          <label>
            Account{' '}
            <select value={selected ?? ''} disabled={busy} onChange={(e) => setAccountId(Number(e.target.value))}>
              {importable.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </label>
          <div className="dropzone" onDragOver={(e) => e.preventDefault()} onDrop={onDrop}>
            <p>{busy ? 'Importing…' : 'Drop an Apple Card CSV here, or choose a file'}</p>
            <input
              type="file"
              accept=".csv,text/csv"
              disabled={busy}
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) void upload(file)
                e.target.value = ''
              }}
            />
          </div>
        </>
      )}
      {error && <p className="error">{error}</p>}
      {summary && (
        <div className="summary">
          <p>
            <strong>{summary.rows_added}</strong> added, <strong>{summary.rows_skipped}</strong> skipped as
            duplicates{summary.flagged > 0 && <>, {summary.flagged} with an unrecognized type</>}.
          </p>
          {summary.errors.length > 0 && (
            <>
              <p className="error">{summary.errors.length} row(s) could not be read and were skipped:</p>
              <ul>
                {summary.errors.map((e) => (
                  <li key={e.line}>
                    Line {e.line}: {e.message}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </section>
  )
}
