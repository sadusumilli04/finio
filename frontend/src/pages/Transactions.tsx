import { useEffect, useState } from 'react'
import { api, type Filters, type Transaction } from '../api'
import AddTransactionForm from '../components/AddTransactionForm'
import FilterBar from '../components/FilterBar'
import { formatCents } from '../lib/money'
import { useFetch } from '../lib/useFetch'

const PAGE_SIZE = 50

export default function Transactions() {
  const [filters, setFilters] = useState<Filters>({})
  const [q, setQ] = useState('')
  const [categoryId, setCategoryId] = useState('')
  const [sort, setSort] = useState('date')
  const [order, setOrder] = useState<'asc' | 'desc'>('desc')
  const [page, setPage] = useState(0)
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState<Transaction | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const categories = useFetch(api.categories, [])
  const txns = useFetch(
    () => api.transactions({ ...filters, q, category_id: categoryId, sort, order, limit: PAGE_SIZE, offset: page * PAGE_SIZE }),
    [filters, q, categoryId, sort, order, page],
  )

  useEffect(() => setPage(0), [filters, q, categoryId, sort, order])

  async function recategorize(t: Transaction, newCategoryId: number) {
    await api.updateTransaction(t.id, { category_id: newCategoryId })
    txns.reload()
  }

  async function makeRule(t: Transaction) {
    if (!window.confirm(`Always categorize merchants containing "${t.merchant}" as ${t.category}?`)) return
    await api.createRule({ match_field: 'merchant', match_type: 'contains', pattern: t.merchant, category_id: t.category_id })
    const { updated } = await api.reapplyRules()
    setNotice(`Rule created; ${updated} transaction(s) recategorized.`)
    txns.reload()
  }

  async function remove(t: Transaction) {
    if (!window.confirm(`Delete ${t.merchant} on ${t.transaction_date}?`)) return
    await api.deleteTransaction(t.id)
    txns.reload()
  }

  const total = txns.data?.total ?? 0
  const lastPage = Math.max(0, Math.ceil(total / PAGE_SIZE) - 1)

  return (
    <section>
      <h1>Transactions</h1>
      <FilterBar filters={filters} onChange={setFilters} />
      <div className="form-row">
        <input placeholder="Search merchant or description" value={q} onChange={(e) => setQ(e.target.value)} />
        <select value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
          <option value="">All categories</option>
          {categories.data?.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <select value={`${sort}:${order}`} onChange={(e) => {
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
        <button type="button" onClick={() => { setAdding(true); setEditing(null) }}>
          Add transaction
        </button>
      </div>

      {(adding || editing) && (
        <AddTransactionForm
          key={editing?.id ?? 'new'}
          initial={editing ?? undefined}
          onCancel={() => { setAdding(false); setEditing(null) }}
          onDone={() => { setAdding(false); setEditing(null); txns.reload() }}
        />
      )}

      {notice && <p className="muted">{notice}</p>}
      {txns.error && <p className="error">{txns.error}</p>}

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
          {txns.data?.items.map((t) => (
            <tr key={t.id}>
              <td>{t.transaction_date}</td>
              <td title={t.description}>{t.merchant}</td>
              <td>
                <select value={t.category_id} onChange={(e) => void recategorize(t, Number(e.target.value))}>
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
    </section>
  )
}
