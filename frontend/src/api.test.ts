import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from './api'

let requested: string[] = []

beforeEach(() => {
  requested = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      requested.push(url)
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
