import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Filters, type Transaction } from '../api'
import AddTransactionForm from '../components/AddTransactionForm'
import FilterBar from '../components/FilterBar'
import RowMenu from '../components/RowMenu'
import SplitPanel from '../components/SplitPanel'
import { amountBounds } from '../lib/amountBounds'
import { categoryColor } from '../lib/categoryColor'
import { shortDate } from '../lib/date'
import { buildChips, type Chip } from '../lib/filterChips'
import { formatCents } from '../lib/money'
import { mergePinned, replacePinned } from '../lib/pinnedRows'
import { useFetch } from '../lib/useFetch'

const PAGE_SIZE = 50

export default function Transactions() {
  const [filters, setFilters] = useState<Filters>({})
  const [q, setQ] = useState('')
  const [categoryId, setCategoryId] = useState('')
  const [sort, setSort] = useState('date')
  const [order, setOrder] = useState<'asc' | 'desc'>('desc')
  const [minText, setMinText] = useState('')
  const [maxText, setMaxText] = useState('')
  const [page, setPage] = useState(0)
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState<Transaction | null>(null)
  const [splitting, setSplitting] = useState<Transaction | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  // Rows just recategorized stay visible (highlighted) even if the active filters no longer match them,
  // so "Make rule" can still be clicked. Cleared whenever the filters, sort or page change.
  const [pinned, setPinned] = useState<Transaction[]>([])

  const bounds = amountBounds(minText, maxText)
  const minCents = bounds.min
  const maxCents = bounds.max
  const amountProblem = bounds.rangeError ?? bounds.minError ?? bounds.maxError

  const categories = useFetch(api.categories, [])
  const accounts = useFetch(api.accounts, [])
  const txns = useFetch(
    () =>
      api.transactions({
        ...filters, q, category_id: categoryId, min_amount: minCents, max_amount: maxCents,
        sort, order, limit: PAGE_SIZE, offset: page * PAGE_SIZE,
      }),
    [filters, q, categoryId, minCents, maxCents, sort, order, page],
  )

  useEffect(() => setPage(0), [filters, q, categoryId, minCents, maxCents, sort, order])
  useEffect(() => setPinned([]), [filters, q, categoryId, minCents, maxCents, sort, order, page])

  const chips = buildChips(filters, {
    accountName: (id) => accounts.data?.find((a) => String(a.id) === id)?.name,
    minText,
    maxText,
  })
  const hasAnyFilter = chips.length > 0 || q !== '' || categoryId !== ''

  function removeChip(key: Chip['key']) {
    if (key === 'date') setFilters((f) => ({ ...f, date_from: undefined, date_to: undefined }))
    else if (key === 'cardholder') setFilters((f) => ({ ...f, cardholder: undefined }))
    else if (key === 'account') setFilters((f) => ({ ...f, account_id: undefined }))
    else {
      setMinText('')
      setMaxText('')
    }
  }

  function clearAllFilters() {
    setFilters({})
    setMinText('')
    setMaxText('')
  }

  const messageOf = (err: unknown) => (err instanceof Error ? err.message : String(err))

  async function recategorize(t: Transaction, newCategoryId: number) {
    setActionError(null)
    setNotice(null)
    try {
      const updated = await api.updateTransaction(t.id, { category_id: newCategoryId })
      setPinned((prev) => [updated, ...prev.filter((p) => p.id !== updated.id)])
    } catch (err) {
      setActionError(messageOf(err))
    } finally {
      txns.reload()
    }
  }

  async function makeRule(t: Transaction) {
    if (!window.confirm(`Always categorize merchants containing "${t.merchant}" as ${t.category}?`)) return
    setActionError(null)
    setNotice(null)
    let created = false
    try {
      await api.createRule({ match_field: 'merchant', match_type: 'contains', pattern: t.merchant, category_id: t.category_id })
      created = true
      const { updated } = await api.reapplyRules()
      setNotice(`Rule created; ${updated} transaction(s) recategorized.`)
    } catch (err) {
      setActionError(
        created
          ? `The rule was created, but re-applying it failed: ${messageOf(err)}. Do not add it again.`
          : messageOf(err),
      )
    } finally {
      txns.reload()
    }
  }

  async function remove(t: Transaction) {
    if (!window.confirm(`Delete ${t.merchant} on ${t.transaction_date}?`)) return
    setActionError(null)
    setNotice(null)
    try {
      await api.deleteTransaction(t.id)
      setPinned((prev) => prev.filter((p) => p.id !== t.id))
      txns.reload()
    } catch (err) {
      setActionError(messageOf(err))
    }
  }

  async function removeSplit(t: Transaction) {
    setActionError(null)
    setNotice(null)
    try {
      const updated = await api.updateTransaction(t.id, { my_share: null })
      setPinned((prev) => replacePinned(prev, updated))
      txns.reload()
    } catch (err) {
      setActionError(messageOf(err))
    }
  }

  const merged = txns.data ? mergePinned(txns.data.items, pinned) : null
  const total = txns.data?.total ?? 0
  const lastPage = Math.max(0, Math.ceil(total / PAGE_SIZE) - 1)
  const firstShown = total === 0 ? 0 : page * PAGE_SIZE + 1
  const lastShown = Math.min(total, (page + 1) * PAGE_SIZE)

  return (
    <section className="txn-page">
      <header className="txn-head">
        <h1>Transactions</h1>
        <button type="button" className="btn btn-primary" onClick={() => { setAdding(true); setEditing(null); setSplitting(null) }}>
          Add transaction
        </button>
      </header>

      <div className="txn-toolbar">
        <input
          className="txn-search"
          type="search"
          aria-label="Search merchant or description"
          placeholder="Search merchant or description"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <select aria-label="Filter by category" value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
          <option value="">All categories</option>
          {categories.data?.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <select
          aria-label="Sort order"
          value={`${sort}:${order}`}
          onChange={(e) => {
            const [s, o] = e.target.value.split(':')
            setSort(s)
            setOrder(o as 'asc' | 'desc')
          }}
        >
          <option value="date:desc">Newest first</option>
          <option value="date:asc">Oldest first</option>
          <option value="amount:desc">Largest first</option>
          <option value="amount:asc">Smallest first</option>
          <option value="merchant:asc">Merchant A–Z</option>
        </select>
        <button
          type="button"
          className="btn"
          aria-expanded={filtersOpen}
          aria-controls="txn-filter-panel"
          onClick={() => setFiltersOpen((o) => !o)}
        >
          Filters
          {chips.length > 0 && <span className="badge">{chips.length}</span>}
        </button>
      </div>

      {filtersOpen && (
        <div className="txn-filter-panel" id="txn-filter-panel">
          <FilterBar filters={filters} onChange={setFilters} />
          <div className="txn-amounts">
            <label>
              Min amount ($)
              <input inputMode="decimal" size={8} value={minText} onChange={(e) => setMinText(e.target.value)} />
            </label>
            <label>
              Max amount ($)
              <input inputMode="decimal" size={8} value={maxText} onChange={(e) => setMaxText(e.target.value)} />
            </label>
          </div>
          <p className="muted small">Amounts are what you spent on each transaction (your share, if it is split); payments and refunds are negative.</p>
        </div>
      )}

      {chips.length > 0 && (
        <div className="txn-chips">
          {chips.map((chip) => (
            <span className="chip" key={chip.key}>
              {chip.label}
              <button type="button" aria-label={`Remove filter: ${chip.label}`} onClick={() => removeChip(chip.key)}>
                ×
              </button>
            </span>
          ))}
          <button type="button" className="link-button" onClick={clearAllFilters}>
            Clear all
          </button>
        </div>
      )}
      {amountProblem && <p className="error">{amountProblem}</p>}

      {(adding || editing) && (
        <AddTransactionForm
          key={editing?.id ?? 'new'}
          initial={editing ?? undefined}
          onCancel={() => { setAdding(false); setEditing(null) }}
          onDone={() => { setAdding(false); setEditing(null); txns.reload() }}
        />
      )}

      {splitting && (
        <SplitPanel
          key={splitting.id}
          transaction={splitting}
          onCancel={() => setSplitting(null)}
          onDone={(updated) => { setSplitting(null); setPinned((prev) => replacePinned(prev, updated)); txns.reload() }}
        />
      )}

      {notice && <p className="muted">{notice}</p>}
      {actionError && <p className="error">{actionError}</p>}
      {txns.error && <p className="error">{txns.error}</p>}
      {!txns.error && txns.data === null && <p className="muted">Loading…</p>}
      {!txns.error && txns.data !== null && (
        <div className={txns.loading ? 'stale' : undefined}>
          <table className="txn-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Merchant</th>
                <th>Category</th>
                <th className="num">Amount</th>
                <th>
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {merged?.rows.map((t) => (
                <tr key={t.id} className={merged.recentIds.has(t.id) ? 'recent' : undefined}>
                  <td className="cell-date">{shortDate(t.transaction_date)}</td>
                  <td className="cell-merchant">
                    <div className="merchant-cell">
                      <span className="dot" style={{ background: categoryColor(t.category_id, t.category) }} aria-hidden="true" />
                      <span className="merchant-text">
                        <span className="merchant-name" title={t.description}>{t.merchant}</span>
                        <span className="merchant-sub">
                          {t.account_name}
                          {t.cardholder ? ` · ${t.cardholder}` : ''}
                        </span>
                      </span>
                    </div>
                  </td>
                  <td className="cell-category">
                    <select
                      className="category-select"
                      aria-label={`Category for ${t.merchant}`}
                      value={t.category_id}
                      onChange={(e) => void recategorize(t, Number(e.target.value))}
                    >
                      {categories.data?.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className={`num cell-amount ${t.effective_amount < 0 ? 'neg' : ''}`}>
                    {formatCents(t.effective_amount)}
                    {t.my_share !== null && <span className="amount-of">of {formatCents(t.amount)}</span>}
                  </td>
                  <td className="cell-actions">
                    <RowMenu
                      label={`Actions for ${t.merchant}`}
                      items={[
                        ...(t.type === 'purchase'
                          ? t.my_share === null
                            ? [{ label: 'Split…', onSelect: () => { setSplitting(t); setAdding(false); setEditing(null) } }]
                            : [
                                { label: 'Edit split…', onSelect: () => { setSplitting(t); setAdding(false); setEditing(null) } },
                                { label: 'Remove split', onSelect: () => void removeSplit(t) },
                              ]
                          : []),
                        { label: 'Make rule', onSelect: () => void makeRule(t) },
                        ...(t.origin === 'manual'
                          ? [
                              { label: 'Edit', onSelect: () => { setEditing(t); setAdding(false); setSplitting(null) } },
                              { label: 'Delete', onSelect: () => void remove(t), danger: true },
                            ]
                          : []),
                      ]}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {merged?.rows.length === 0 && !txns.loading && (
            <p className="muted txn-empty">
              {hasAnyFilter ? (
                'No transactions match these filters.'
              ) : (
                <>
                  No transactions yet. <Link to="/import">Import a statement</Link> or add one.
                </>
              )}
            </p>
          )}
          {merged && merged.hiddenCount > 0 && (
            <p className="muted small">
              Highlighted rows were just recategorized and no longer match these filters. They stay listed until you change the filters.
            </p>
          )}
          <div className="txn-pager">
            <span className="muted">
              {total === 0 ? '0 transactions' : `Showing ${firstShown}–${lastShown} of ${total.toLocaleString('en-US')}`}
            </span>
            <span className="txn-pager-buttons">
              <button type="button" className="btn" disabled={page === 0} onClick={() => setPage(page - 1)}>
                Previous
              </button>
              <button type="button" className="btn" disabled={page >= lastPage} onClick={() => setPage(page + 1)}>
                Next
              </button>
            </span>
          </div>
        </div>
      )}
    </section>
  )
}
