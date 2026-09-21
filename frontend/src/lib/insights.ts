import type { InsightRank, SubscriptionKind } from '../api'
import { formatCents } from './money'

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

export function monthLabel(key: string, inProgress = false): string {
  const [year, month] = key.split('-')
  return `${MONTHS[Number(month) - 1]} ${year}${inProgress ? ' (in progress)' : ''}`
}

export function neighborMonth(available: string[], month: string, step: 1 | -1): string | null {
  const at = available.indexOf(month)
  if (at === -1) return null
  return available[at + step] ?? null
}

/** Keep the chosen month only if it is one of the available months; otherwise undefined, meaning "the default month". */
export function keepMonth(available: string[], month: string | undefined): string | undefined {
  return month !== undefined && available.includes(month) ? month : undefined
}

export function formatPercent(pct: number): string {
  if (pct === 0) return '0%'
  const text = Number.isInteger(pct) ? String(pct) : pct.toFixed(1)
  return `${pct > 0 ? '+' : ''}${text}%`
}

export function changeText(change: number, pct: number | null, comparedWith: string): string {
  if (change === 0) return `Same as ${comparedWith}`
  const percent = pct === null ? '' : ` (${formatPercent(pct)})`
  return `${change > 0 ? 'Up' : 'Down'} ${formatCents(Math.abs(change))}${percent} vs ${comparedWith}`
}

export function paceText(daysElapsed: number, daysInMonth: number, projected: number | null): string {
  const day = `Day ${daysElapsed} of ${daysInMonth}`
  return projected === null ? day : `${day} · on pace for ${formatCents(projected)}`
}

function ordinal(n: number): string {
  const teen = n % 100 >= 11 && n % 100 <= 13
  const suffix = teen ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' } as Record<number, string>)[n % 10] ?? 'th'
  return `${n}${suffix}`
}

export function rankText(rank: InsightRank): string {
  return `${ordinal(rank.position)} highest of ${rank.of} months`
}

const TAGS: Record<SubscriptionKind, string> = {
  price_up: 'Price up',
  price_down: 'Price down',
  new: 'New',
  missing: 'Missing',
}

export function subscriptionTag(kind: SubscriptionKind): string {
  return TAGS[kind]
}
