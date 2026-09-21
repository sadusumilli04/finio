import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, type Filters } from '../api'
import FilterBar from '../components/FilterBar'
import { categoryColor } from '../lib/categoryColor'
import { withShares } from '../lib/categoryShares'
import { formatCents } from '../lib/money'
import { median } from '../lib/stats'
import { useFetch } from '../lib/useFetch'

type CategoryView = 'bars' | 'pie' | 'both'
const VIEWS: { value: CategoryView; label: string }[] = [
  { value: 'bars', label: 'Bars' },
  { value: 'pie', label: 'Pie' },
  { value: 'both', label: 'Both' },
]
const VIEW_KEY = 'finio.categoryView'

function rememberedView(): CategoryView {
  try {
    const saved = localStorage.getItem(VIEW_KEY)
    return VIEWS.some((v) => v.value === saved) ? (saved as CategoryView) : 'bars'
  } catch {
    return 'bars'
  }
}

export default function Dashboard() {
  const [filters, setFilters] = useState<Filters>({})
  const [view, setView] = useState<CategoryView>(rememberedView)

  function chooseView(next: CategoryView) {
    setView(next)
    try {
      localStorage.setItem(VIEW_KEY, next)
    } catch {
      /* storage unavailable; the choice just isn't remembered */
    }
  }
  const byCategory = useFetch(() => api.spendingByCategory(filters), [filters])
  const trends = useFetch(() => api.trends(filters), [filters])
  const merchants = useFetch(() => api.topMerchants(filters), [filters])

  const grandTotal = byCategory.data?.reduce((sum, c) => sum + c.total, 0) ?? 0
  const shares = withShares(byCategory.data ?? [])
  // A median needs at least two months to say anything the bars don't already show.
  const monthlyMedian = trends.data && trends.data.length >= 2 ? median(trends.data.map((t) => t.total)) : null
  const errors = [...new Set([byCategory.error, trends.error, merchants.error].filter((e): e is string => !!e))]
  const notLoaded = byCategory.data === null || trends.data === null || merchants.data === null
  const refetching = byCategory.loading || trends.loading || merchants.loading

  return (
    <section>
      <h1>Dashboard</h1>
      <FilterBar filters={filters} onChange={setFilters} presets />
      {errors.length > 0 ? (
        <p className="error">{errors.join(' · ')}</p>
      ) : notLoaded ? (
        <p className="muted">Loading…</p>
      ) : byCategory.data?.length === 0 ? (
        <p className="muted">No spending in this range. Import a statement or add a transaction to get started.</p>
      ) : (
        <div className={refetching ? 'stale' : undefined}>
          <p>
            Total spending: <strong>{formatCents(grandTotal)}</strong>
          </p>
          <div className="grid-2">
            <div className={`panel${view === 'both' ? ' wide' : ''}`}>
              <div className="panel-head">
                <h2>By category</h2>
                <div className="segmented" role="group" aria-label="Chart type">
                  {VIEWS.map((v) => (
                    <button key={v.value} type="button" aria-pressed={view === v.value} onClick={() => chooseView(v.value)}>
                      {v.label}
                    </button>
                  ))}
                </div>
              </div>
              <div className={view === 'both' ? 'chart-pair' : undefined}>
                {view !== 'pie' && (
                  <ResponsiveContainer width="100%" height={320}>
                    <BarChart data={shares} layout="vertical" margin={{ left: 20 }}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis type="number" tickFormatter={(v) => formatCents(Number(v))} />
                      <YAxis type="category" dataKey="category" width={110} />
                      <Tooltip formatter={(v) => formatCents(Number(v))} />
                      <Bar dataKey="total" name="Spending">
                        {shares.map((c) => (
                          <Cell key={c.category_id} fill={categoryColor(c.category_id, c.category)} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                )}
                {view !== 'bars' && (
                  <div className="pie-view" aria-label="Spending by category, pie chart" role="group">
                    <ResponsiveContainer width="100%" height={240}>
                      <PieChart>
                        <Pie data={shares} dataKey="total" nameKey="category" outerRadius="90%" stroke="#fff" strokeWidth={2}>
                          {shares.map((c) => (
                            <Cell key={c.category_id} fill={categoryColor(c.category_id, c.category)} />
                          ))}
                        </Pie>
                        <Tooltip formatter={(v) => formatCents(Number(v))} />
                      </PieChart>
                    </ResponsiveContainer>
                    <ul className="pie-legend">
                      {shares.map((c) => (
                        <li key={c.category_id}>
                          <span className="swatch" style={{ background: categoryColor(c.category_id, c.category) }} aria-hidden="true" />
                          <span className="legend-name">{c.category}</span>
                          <span className="legend-amount">{formatCents(c.total)}</span>
                          <span className="legend-percent">{c.percent.toFixed(1)}%</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
            <div className={`panel${view === 'both' ? ' wide' : ''}`}>
              <h2>Monthly trend</h2>
              {monthlyMedian !== null && (
                <p className="muted">
                  <span className="median-swatch" aria-hidden="true" />
                  Median month: {formatCents(monthlyMedian)}
                </p>
              )}
              <ResponsiveContainer width="100%" height={320}>
                <BarChart data={trends.data ?? []}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="month" />
                  <YAxis tickFormatter={(v) => formatCents(Number(v))} width={90} />
                  <Tooltip formatter={(v) => formatCents(Number(v))} />
                  <Bar dataKey="total" name="Spending" fill="#3b6ea5" />
                  {monthlyMedian !== null && (
                    <ReferenceLine y={monthlyMedian} stroke="#1b2421" strokeWidth={2} strokeDasharray="6 4" />
                  )}
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
          <div className="panel">
            <h2>Top merchants</h2>
            <table>
              <thead>
                <tr>
                  <th>Merchant</th>
                  <th className="num">Transactions</th>
                  <th className="num">Total</th>
                </tr>
              </thead>
              <tbody>
                {merchants.data?.map((m) => (
                  <tr key={m.merchant}>
                    <td>{m.merchant}</td>
                    <td className="num">{m.count}</td>
                    <td className="num">{formatCents(m.total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  )
}
