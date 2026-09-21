import { toQueryString } from './lib/query'

export type AccountType = 'credit_card' | 'checking' | 'savings' | 'other'
export type AccountSource = 'apple_card_csv' | 'manual'
export type Account = {
  id: number
  name: string
  type: AccountType
  source: AccountSource
  starting_balance: number
  starting_balance_date: string | null
  transaction_count: number
}
export type Category = { id: number; name: string; parent_id: number | null }
export type Direction = 'expense' | 'income' | 'refund'
export type Transaction = {
  id: number
  account_id: number
  account_name: string
  transaction_date: string
  posted_date: string | null
  amount: number
  type: string
  merchant: string
  description: string
  cardholder: string | null
  category_id: number
  category: string
  category_source: 'source_default' | 'rule' | 'manual'
  origin: 'import' | 'manual'
  my_share: number | null
  share_source: 'manual' | 'venmo' | null
  effective_amount: number
}
export type TransactionPage = { items: Transaction[]; total: number }
export type Filters = {
  date_from?: string
  date_to?: string
  cardholder?: string
  account_id?: string
  category_id?: string
}
export type MerchantSort = 'spent' | 'visits'
export type ManualTransactionInput = {
  account_id: number
  date: string
  amount: number
  direction: Direction
  merchant: string
  description?: string | null
  cardholder?: string | null
  category_id: number
}
export type ImportSummary = {
  batch_id: number
  rows_total: number
  rows_added: number
  rows_skipped: number
  flagged: number
  errors: { line: number; message: string }[]
}
export type CategoryTotal = { category_id: number; category: string; total: number; count: number }
export type MonthTotal = { month: string; total: number }
export type MerchantTotal = { merchant: string; total: number; count: number }
export type RecurringCharge = {
  merchant: string
  cadence: 'weekly' | 'biweekly' | 'monthly' | 'yearly'
  typical_amount: number
  count: number
  last_date: string
  next_expected: string
}

export type InsightRank = { position: number; of: number }
export type InsightSummary = {
  total: number
  compared_with: string
  previous_total: number
  change: number
  change_pct: number | null
  typical_total: number | null
  rank: InsightRank | null
  projected_total: number | null
}
export type CategoryMover = { category: string; category_id: number; current: number; previous: number; change: number; change_pct: number | null }
export type NewMerchant = { merchant: string; total: number; count: number }
export type GrowingMerchant = { merchant: string; current: number; previous: number; change: number; change_pct: number | null }
export type UnusualCharge = { transaction_id: number; date: string; merchant: string; category: string; amount: number; typical: number }
export type SubscriptionKind = 'missing' | 'price_up' | 'price_down' | 'new'
export type SubscriptionChange = { merchant: string; kind: SubscriptionKind; current: number | null; previous: number | null; expected_date: string | null }
export type Insights = {
  month: string
  in_progress: boolean
  as_of: string | null
  days_elapsed: number
  days_in_month: number
  available_months: string[]
  summary: InsightSummary
  movers: { up: CategoryMover[]; down: CategoryMover[] }
  new_merchants: NewMerchant[]
  growing_merchants: GrowingMerchant[]
  unusual_charges: UnusualCharge[]
  subscriptions: SubscriptionChange[]
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, init)
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* keep statusText */
    }
    throw new Error(detail)
  }
  return res.status === 204 ? (undefined as T) : res.json()
}

const send = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: body === undefined ? undefined : JSON.stringify(body),
})

export const api = {
  accounts: () => request<Account[]>('/accounts'),
  createAccount: (body: { name: string; type: AccountType; source: AccountSource }) =>
    request<Account>('/accounts', send('POST', body)),
  deleteAccount: (id: number) => request<void>(`/accounts/${id}`, send('DELETE')),
  categories: () => request<Category[]>('/categories'),
  cardholders: () => request<string[]>('/cardholders'),
  merchants: () => request<string[]>('/merchants'),

  transactions: (params: Record<string, string | number | undefined>) =>
    request<TransactionPage>(`/transactions${toQueryString(params)}`),
  createTransaction: (body: ManualTransactionInput) => request<Transaction>('/transactions', send('POST', body)),
  updateTransaction: (id: number, patch: Partial<Omit<ManualTransactionInput, 'account_id'>> & { my_share?: number | null }) =>
    request<Transaction>(`/transactions/${id}`, send('PATCH', patch)),
  deleteTransaction: (id: number) => request<void>(`/transactions/${id}`, send('DELETE')),

  createRule: (body: {
    match_field: 'merchant' | 'description'
    match_type: 'contains' | 'equals'
    pattern: string
    category_id: number
  }) => request<unknown>('/rules', send('POST', body)),
  reapplyRules: () => request<{ updated: number }>('/rules/reapply', send('POST')),

  importFile: (accountId: number, file: File) => {
    const form = new FormData()
    form.set('account_id', String(accountId))
    form.set('file', file)
    return request<ImportSummary>('/imports', { method: 'POST', body: form })
  },

  spendingByCategory: (f: Filters) => request<CategoryTotal[]>(`/analytics/spending-by-category${toQueryString(f)}`),
  trends: (f: Filters) => request<MonthTotal[]>(`/analytics/trends${toQueryString(f)}`),
  topMerchants: (f: Filters, opts: { limit?: number; sort?: MerchantSort } = {}) =>
    request<MerchantTotal[]>(`/analytics/top-merchants${toQueryString({ ...f, ...opts })}`),
  insights: (month?: string, cardholder?: string) => request<Insights>(`/insights${toQueryString({ month, cardholder })}`),
  recurring: (f: Filters) => request<RecurringCharge[]>(`/analytics/recurring${toQueryString(f)}`),
}
