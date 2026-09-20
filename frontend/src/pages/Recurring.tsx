import { useState } from 'react'
import { api, type Filters } from '../api'
import FilterBar from '../components/FilterBar'
import { formatCents } from '../lib/money'
import { useFetch } from '../lib/useFetch'

export default function Recurring() {
  const [filters, setFilters] = useState<Filters>({})
  const recurring = useFetch(() => api.recurring(filters), [filters])

  return (
    <section>
      <h1>Recurring charges</h1>
      <FilterBar filters={filters} onChange={setFilters} />
      {recurring.error ? (
        <p className="error">{recurring.error}</p>
      ) : recurring.data === null ? (
        <p className="muted">Loading…</p>
      ) : recurring.data.length === 0 ? (
        <p className="muted">
          Nothing detected yet. A charge counts as recurring after 3 similar payments at a regular interval.
        </p>
      ) : (
        <table className={recurring.loading ? 'stale' : undefined}>
          <thead>
            <tr>
              <th>Merchant</th>
              <th>Cadence</th>
              <th className="num">Typical amount</th>
              <th className="num">Charges</th>
              <th>Last charged</th>
              <th>Next expected</th>
            </tr>
          </thead>
          <tbody>
            {recurring.data.map((r) => (
              <tr key={r.merchant}>
                <td>{r.merchant}</td>
                <td>{r.cadence}</td>
                <td className="num">{formatCents(r.typical_amount)}</td>
                <td className="num">{r.count}</td>
                <td>{r.last_date}</td>
                <td>{r.next_expected}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
