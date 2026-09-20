import { useEffect, useState } from 'react'
import { api, type Filters, type Transaction } from '../api'
import AddTransactionForm from '../components/AddTransactionForm'
import FilterBar from '../components/FilterBar'
import { amountBounds } from '../lib/amountBounds'
import { formatCents } from '../lib/money'
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
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState<Transaction | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  const bounds = amountBounds(minText, maxText)
  const minCents = bounds.min
  const maxCents = bounds.max

  const categories = useFetch(api.categories, [])
  const txns = useFetch(
    () =>
      api.transactions({
        ...filters, q, category_id: categoryId, min_amount: minCents, max_amount: maxCents,
        sort, order, limit: PAGE_SIZE, offset: page * PAGE_SIZE,
      }),
    [filters, q, categoryId, minCents, maxCents, sort, order, page],
  )

  useEffect(() => setPage(0), [filters, q, categoryId, minCents, maxCents, sort, order])

  const messageOf = (err: unknown) => (err instanceof Error ? err.message : String(err))

  async function recategorize(t: Transaction, newCategoryId: number) {
    setActionError(null)
    setNotice(null)
    try {
      await api.updateTransaction(t.id, { category_id: newCategoryId })
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
      txns.reload()
    } catch (err) {
      setActionError(messageOf(err))
    }
  }

  const total = txns.data?.total ?? 0
  const lastPage = Math.max(0, Math.ceil(total / PAGE_SIZE) - 1)

  return (
    <section>
      <h1>Transactions</h1>
      <FilterBar filters={filters} onChange={setFilters} />
      <div className="form-row">
        <input aria-label="Search merchant or description" placeholder="Search merchant or description" value={q} onChange={(e) => setQ(e.target.value)} />
        <select aria-label="Filter by category" value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
          <option value="">All categories</option>
          {categories.data?.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <select aria-label="Sort order" value={`${sort}:${order}`} onChange={(e) => {
          const [s, o] = e.target.value.split(':')
          setSort(s)
          setOrder(o as 'asc' | 'desc')
        }}>
          <option value="date:desc">Newest first</option>
          <option value="date:asc">Oldest first</option>
          <option value="amount:desc">Largest first</option>
          <option value="amount:asc">Smallest first</option>
          <option value="merchant:asc">Merchant A–Z</option>
        </select>
        <label>
          Min amount ($){' '}
          <input inputMode="decimal" size={8} value={minText} onChange={(e) => setMinText(e.target.value)} />
        </label>
        {bounds.minError && <span className="error">{bounds.minError}</span>}
        <label>
          Max amount ($){' '}
          <input inputMode="decimal" size={8} value={maxText} onChange={(e) => setMaxText(e.target.value)} />
        </label>
        {bounds.maxError && <span className="error">{bounds.maxError}</span>}
        <button type="button" onClick={() => { setAdding(true); setEditing(null) }}>
          Add transaction
        </button>
      </div>
      {bounds.rangeError && <p className="error">{bounds.rangeError}</p>}
      <p className="muted">Amounts are per transaction; payments and refunds are negative.</p>

      {(adding || editing) && (
        <AddTransactionForm
          key={editing?.id ?? 'new'}
          initial={editing ?? undefined}
          onCancel={() => { setAdding(false); setEditing(null) }}
          onDone={() => { setAdding(false); setEditing(null); txns.reload() }}
        />
      )}

      {notice && <p className="muted">{notice}</p>}
      {actionError && <p className="error">{actionError}</p>}
      {txns.error && <p className="error">{txns.error}</p>}
      {!txns.error && txns.data === null && <p className="muted">Loading…</p>}
      {!txns.error && txns.data !== null && (
        <div className={txns.loading ? 'stale' : undefined}>
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Merchant</th>
              <th>Category</th>
              <th>Account</th>
              <th>Cardholder</th>
              <th className="num">Amount</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {txns.data.items.map((t) => (
              <tr key={t.id}>
                <td>{t.transaction_date}</td>
                <td title={t.description}>{t.merchant}</td>
                <td>
                  <select aria-label={`Category for ${t.merchant}`} value={t.category_id} onChange={(e) => void recategorize(t, Number(e.target.value))}>
                    {categories.data?.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </td>
                <td>{t.account_name}</td>
                <td>{t.cardholder ?? ''}</td>
                <td className={`num ${t.amount < 0 ? 'neg' : ''}`}>{formatCents(t.amount)}</td>
                <td>
                  <button type="button" onClick={() => void makeRule(t)}>Make rule</button>{' '}
                  {t.origin === 'manual' && (
                    <>
                      <button type="button" onClick={() => { setEditing(t); setAdding(false) }}>Edit</button>{' '}
                      <button type="button" onClick={() => void remove(t)}>Delete</button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {txns.data?.items.length === 0 && !txns.loading && <p className="muted">No transactions match.</p>}
        <div className="pager">
          <button type="button" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</button>
          <span>
            Page {page + 1} of {lastPage + 1} · {total} transactions
          </span>
          <button type="button" disabled={page >= lastPage} onClick={() => setPage(page + 1)}>Next</button>
        </div>
        </div>
      )}
    </section>
  )
}
