import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from './api'

let requested: string[] = []
let requestedInit: (RequestInit | undefined)[] = []

beforeEach(() => {
  requested = []
  requestedInit = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      requested.push(url)
      requestedInit.push(init)
      return { ok: true, status: 200, json: async () => [] }
    }),
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('api.topMerchants', () => {
  it('asks for the default list when no options are given', async () => {
    await api.topMerchants({})
    expect(requested).toEqual(['/api/analytics/top-merchants'])
  })

  it('sends the count and the ranking', async () => {
    await api.topMerchants({}, { limit: 25, sort: 'visits' })
    expect(requested).toEqual(['/api/analytics/top-merchants?limit=25&sort=visits'])
  })

  it('combines the options with the dashboard filters, including the category', async () => {
    await api.topMerchants({ date_from: '2026-09-01', category_id: '3' }, { limit: 5, sort: 'spent' })
    const query = new URLSearchParams(requested[0].split('?')[1])
    expect(Object.fromEntries(query)).toEqual({ date_from: '2026-09-01', category_id: '3', limit: '5', sort: 'spent' })
  })
})

describe('the category filter on the other dashboard endpoints', () => {
  it('is sent to the category, trend and recurring endpoints too', async () => {
    const filters = { category_id: '7' }
    await api.spendingByCategory(filters)
    await api.trends(filters)
    await api.recurring(filters)
    expect(requested).toEqual([
      '/api/analytics/spending-by-category?category_id=7',
      '/api/analytics/trends?category_id=7',
      '/api/analytics/recurring?category_id=7',
    ])
  })
})

describe('api.insights', () => {
  it('asks for the default month when none is given', async () => {
    await api.insights()
    expect(requested).toEqual(['/api/insights'])
  })

  it('sends the chosen month', async () => {
    await api.insights('2026-08')
    expect(requested).toEqual(['/api/insights?month=2026-08'])
  })

  it('sends the chosen cardholder, and nothing for everyone', async () => {
    await api.insights('2026-08', 'Ann')
    await api.insights(undefined, 'Ann')
    await api.insights('2026-08', '')
    expect(requested).toEqual(['/api/insights?month=2026-08&cardholder=Ann', '/api/insights?cardholder=Ann', '/api/insights?month=2026-08'])
  })
})

describe('venmo link endpoints', () => {
  it('fetches candidates for a charge', async () => {
    await api.venmoCandidates(42)
    expect(requested).toEqual(['/api/transactions/42/venmo-candidates'])
    expect(requestedInit[0]?.method).toBeUndefined()
  })

  it('fetches the payments already linked to a charge', async () => {
    await api.venmoLinks(42)
    expect(requested).toEqual(['/api/transactions/42/venmo-links'])
    expect(requestedInit[0]?.method).toBeUndefined()
  })

  it('links a Venmo payment to a charge', async () => {
    await api.linkVenmo(42, 7)
    expect(requested).toEqual(['/api/transactions/42/venmo-links'])
    expect(requestedInit[0]?.method).toBe('POST')
    expect(JSON.parse(requestedInit[0]?.body as string)).toEqual({ venmo_transaction_id: 7 })
  })

  it('unlinks a Venmo payment from a charge', async () => {
    await api.unlinkVenmo(42, 7)
    expect(requested).toEqual(['/api/transactions/42/venmo-links/7'])
    expect(requestedInit[0]?.method).toBe('DELETE')
  })
})
