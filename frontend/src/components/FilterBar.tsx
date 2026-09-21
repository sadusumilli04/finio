import { api, type Filters } from '../api'
import { activePreset, DATE_PRESETS, presetRange } from '../lib/datePresets'
import { useFetch } from '../lib/useFetch'

type Props = {
  filters: Filters
  onChange: (f: Filters) => void
  /** Show one-click date ranges (This month, Last month, ...) above the fields. */
  presets?: boolean
}

export default function FilterBar({ filters, onChange, presets = false }: Props) {
  const cardholders = useFetch(api.cardholders, [])
  const accounts = useFetch(api.accounts, [])
  const set = (key: keyof Filters, value: string) => onChange({ ...filters, [key]: value || undefined })
  const activeKey = presets ? activePreset(filters) : null

  return (
    <>
      {presets && (
        <div className="preset-row" role="group" aria-label="Date range">
          {DATE_PRESETS.map((p) => (
            <button
              key={p.key}
              type="button"
              aria-pressed={activeKey === p.key}
              onClick={() => onChange({ ...filters, ...presetRange(p.key) })}
            >
              {p.label}
            </button>
          ))}
        </div>
      )}
      <div className="filter-bar">
        <label>
          From
          <input type="date" value={filters.date_from ?? ''} onChange={(e) => set('date_from', e.target.value)} />
        </label>
        <label>
          To
          <input type="date" value={filters.date_to ?? ''} onChange={(e) => set('date_to', e.target.value)} />
        </label>
        <label>
          Cardholder
          <select value={filters.cardholder ?? ''} onChange={(e) => set('cardholder', e.target.value)}>
            <option value="">All</option>
            {cardholders.data?.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
        <label>
          Account
          <select value={filters.account_id ?? ''} onChange={(e) => set('account_id', e.target.value)}>
            <option value="">All</option>
            {accounts.data?.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        </label>
        <button type="button" onClick={() => onChange({})}>
          Clear
        </button>
      </div>
    </>
  )
}
