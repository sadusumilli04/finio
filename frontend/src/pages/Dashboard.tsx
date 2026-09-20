import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, type Filters } from '../api'
import FilterBar from '../components/FilterBar'
import { formatCents } from '../lib/money'
import { useFetch } from '../lib/useFetch'

export default function Dashboard() {
  const [filters, setFilters] = useState<Filters>({})
  const byCategory = useFetch(() => api.spendingByCategory(filters), [filters])
  const trends = useFetch(() => api.trends(filters), [filters])
  const merchants = useFetch(() => api.topMerchants(filters), [filters])

  const grandTotal = byCategory.data?.reduce((sum, c) => sum + c.total, 0) ?? 0
  const errors = [...new Set([byCategory.error, trends.error, merchants.error].filter((e): e is string => !!e))]
  const notLoaded = byCategory.data === null || trends.data === null || merchants.data === null
  const refetching = byCategory.loading || trends.loading || merchants.loading

  return (
    <section>
      <h1>Dashboard</h1>
      <FilterBar filters={filters} onChange={setFilters} />
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
            <div className="panel">
              <h2>By category</h2>
              <ResponsiveContainer width="100%" height={320}>
                <BarChart data={byCategory.data ?? []} layout="vertical" margin={{ left: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" tickFormatter={(v) => formatCents(Number(v))} />
                  <YAxis type="category" dataKey="category" width={110} />
                  <Tooltip formatter={(v) => formatCents(Number(v))} />
                  <Bar dataKey="total" fill="#2f7d5b" />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="panel">
              <h2>Monthly trend</h2>
              <ResponsiveContainer width="100%" height={320}>
                <BarChart data={trends.data ?? []}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="month" />
                  <YAxis tickFormatter={(v) => formatCents(Number(v))} width={90} />
                  <Tooltip formatter={(v) => formatCents(Number(v))} />
                  <Bar dataKey="total" fill="#3b6ea5" />
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
