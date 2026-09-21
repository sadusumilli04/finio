import type { ReactNode } from 'react'

type Props = {
  title: string
  /** One line on how the card is worked out. */
  note: string
  /** Shown instead of the children when there is nothing to report. */
  empty: string | null
  children?: ReactNode
}

export default function InsightCard({ title, note, empty, children }: Props) {
  return (
    <section className="insight-card">
      <h2>{title}</h2>
      <p className="muted insight-note">{note}</p>
      {empty !== null ? <p className="muted">{empty}</p> : children}
    </section>
  )
}
