import { useEffect, useState } from 'react'
import { api, type CategoryMover, type Insights as InsightsData } from '../api'
import InsightCard from '../components/InsightCard'
import { changeText, formatPercent, keepMonth, monthLabel, neighborMonth, paceText, rankText, subscriptionTag } from '../lib/insights'
import { formatCents } from '../lib/money'
import { useFetch } from '../lib/useFetch'

function Movers({ title, items }: { title: string; items: CategoryMover[] }) {
  return (
    <div>
      <h3>{title}</h3>
      {items.length === 0 ? (
        <p className="muted">None</p>
      ) : (
        <ul className="insight-list">
          {items.map((m) => (
            <li key={m.category_id}>
              <span>{m.category}</span>
              <span className={m.change > 0 ? 'up' : 'down'}>
                {m.change > 0 ? '+' : '-'}
                {formatCents(Math.abs(m.change))} {m.change_pct === null ? '(new)' : `(${formatPercent(m.change_pct)})`}
              </span>
              <span className="muted">
                {formatCents(m.previous)} → {formatCents(m.current)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function Glance({ data }: { data: InsightsData }) {
  const { summary } = data
  return (
    <section className="insight-glance">
      <div className="insight-total">
        {formatCents(summary.total)}
        {data.in_progress && <span className="muted"> so far</span>}
      </div>
      <p className={summary.change > 0 ? 'up' : summary.change < 0 ? 'down' : undefined}>
        {changeText(summary.change, summary.change_pct, summary.compared_with)}
      </p>
      <ul className="insight-facts">
        {summary.typical_total !== null && <li>A typical month: {formatCents(summary.typical_total)}</li>}
        {summary.rank !== null && <li>{rankText(summary.rank)}</li>}
        {data.in_progress && <li>{paceText(data.days_elapsed, data.days_in_month, summary.projected_total)}</li>}
        {summary.typical_total === null && <li className="muted">A typical month needs at least 3 other full months</li>}
      </ul>
    </section>
  )
}

export default function Insights() {
  const [month, setMonth] = useState<string | undefined>(undefined)
  const [person, setPerson] = useState('')
  const cardholders = useFetch(api.cardholders, [])
  const insights = useFetch(() => api.insights(month, person), [month, person])
  const data = insights.data

  // Changing the person keeps the month; if that person has no spending in it, fall back to their default month.
  useEffect(() => {
    if (data && keepMonth(data.available_months, month) !== month) setMonth(undefined)
  }, [data, month])

  const newest = data ? [...data.available_months].reverse() : []
  const previous = data ? neighborMonth(data.available_months, data.month, -1) : null
  const next = data ? neighborMonth(data.available_months, data.month, 1) : null

  return (
    <section className="insights-page">
      <div className="insights-header">
        <h1>Insights</h1>
        <div className="insights-controls">
          <label className="insights-person">
            Person
            <select aria-label="Person" value={person} onChange={(e) => setPerson(e.target.value)}>
              <option value="">Everyone</option>
              {cardholders.data?.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
          {data && data.available_months.length > 0 && (
            <div className="insights-picker">
              <button type="button" aria-label="Previous month" disabled={previous === null} onClick={() => previous && setMonth(previous)}>
                ←
              </button>
              <select aria-label="Month" value={data.month} onChange={(e) => setMonth(e.target.value)}>
                {newest.map((m) => (
                  <option key={m} value={m}>
                    {monthLabel(m, data.in_progress && m === data.month)}
                  </option>
                ))}
              </select>
              <button type="button" aria-label="Next month" disabled={next === null} onClick={() => next && setMonth(next)}>
                →
              </button>
            </div>
          )}
        </div>
      </div>

      {insights.error ? (
        <p className="error">{insights.error}</p>
      ) : data === null ? (
        <p className="muted">Loading…</p>
      ) : data.available_months.length === 0 ? (
        <p className="muted">{person ? 'No spending for this person' : 'Import a statement to see insights.'}</p>
      ) : (
        <div className={insights.loading ? 'stale' : undefined}>
          <Glance data={data} />
          <div className="insight-grid">
            <InsightCard
              title="Biggest movers"
              note={`Category changes of $10 or more against ${data.summary.compared_with}.`}
              empty={data.movers.up.length === 0 && data.movers.down.length === 0 ? 'No big changes by category' : null}
            >
              <Movers title="Went up" items={data.movers.up} />
              <Movers title="Went down" items={data.movers.down} />
            </InsightCard>

            <InsightCard
              title="New merchants"
              note="Places you had not spent at before this month."
              empty={data.new_merchants.length === 0 ? 'No new merchants this month' : null}
            >
              <ul className="insight-list">
                {data.new_merchants.map((m) => (
                  <li key={m.merchant}>
                    <span>{m.merchant}</span>
                    <span>{formatCents(m.total)}</span>
                    <span className="muted">{m.count === 1 ? '1 visit' : `${m.count} visits`}</span>
                  </li>
                ))}
              </ul>
            </InsightCard>

            <InsightCard
              title="Merchants that grew"
              note="Up by $25 or more and at least 1.5 times last month."
              empty={data.growing_merchants.length === 0 ? 'No merchants grew sharply' : null}
            >
              <ul className="insight-list">
                {data.growing_merchants.map((m) => (
                  <li key={m.merchant}>
                    <span>{m.merchant}</span>
                    <span className="up">
                      +{formatCents(m.change)} {m.change_pct !== null && `(${formatPercent(m.change_pct)})`}
                    </span>
                    <span className="muted">
                      {formatCents(m.previous)} → {formatCents(m.current)}
                    </span>
                  </li>
                ))}
              </ul>
            </InsightCard>

            <InsightCard
              title="Unusual charges"
              note="At least 3 times the usual charge in that category, and $50 or more."
              empty={data.unusual_charges.length === 0 ? 'No unusual charges this month' : null}
            >
              <ul className="insight-list">
                {data.unusual_charges.map((u) => (
                  <li key={u.transaction_id}>
                    <span>
                      {u.merchant} <span className="muted">{u.date}</span>
                    </span>
                    <span>{formatCents(u.amount)}</span>
                    <span className="muted">
                      typical for {u.category}: {formatCents(u.typical)}
                    </span>
                  </li>
                ))}
              </ul>
            </InsightCard>

            <InsightCard
              title="Subscription changes"
              note="Monthly charges that changed price, started, or did not show up."
              empty={data.subscriptions.length === 0 ? 'No subscription changes' : null}
            >
              <ul className="insight-list">
                {data.subscriptions.map((s) => (
                  <li key={`${s.merchant}-${s.kind}`}>
                    <span>
                      {s.merchant} <span className={`tag tag-${s.kind}`}>{subscriptionTag(s.kind)}</span>
                    </span>
                    <span>
                      {s.kind === 'missing'
                        ? `expected ${s.expected_date}`
                        : s.previous !== null && s.current !== null
                          ? `${formatCents(s.previous)} → ${formatCents(s.current)}`
                          : s.current !== null
                            ? formatCents(s.current)
                            : ''}
                    </span>
                    <span className="muted">{s.kind === 'missing' && s.previous !== null ? `last ${formatCents(s.previous)}` : ''}</span>
                  </li>
                ))}
              </ul>
            </InsightCard>
          </div>
        </div>
      )}
    </section>
  )
}
