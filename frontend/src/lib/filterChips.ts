import type { Filters } from '../api'
import { shortDate } from './date'

export type Chip = { key: 'date' | 'cardholder' | 'account' | 'amount'; label: string }

type Options = {
  accountName: (id: string) => string | undefined
  minText: string
  maxText: string
}

/** One removable summary chip per active filter, in a stable order. */
export function buildChips(filters: Filters, { accountName, minText, maxText }: Options): Chip[] {
  const chips: Chip[] = []

  if (filters.date_from && filters.date_to) {
    chips.push({ key: 'date', label: `${shortDate(filters.date_from)} – ${shortDate(filters.date_to)}` })
  } else if (filters.date_from) {
    chips.push({ key: 'date', label: `From ${shortDate(filters.date_from)}` })
  } else if (filters.date_to) {
    chips.push({ key: 'date', label: `Until ${shortDate(filters.date_to)}` })
  }

  if (filters.cardholder) chips.push({ key: 'cardholder', label: `Cardholder: ${filters.cardholder}` })

  if (filters.account_id) {
    chips.push({ key: 'account', label: `Account: ${accountName(filters.account_id) ?? filters.account_id}` })
  }

  const min = minText.trim()
  const max = maxText.trim()
  if (min && max) chips.push({ key: 'amount', label: `$${min} – $${max}` })
  else if (min) chips.push({ key: 'amount', label: `Over $${min}` })
  else if (max) chips.push({ key: 'amount', label: `Under $${max}` })

  return chips
}
