import { describe, expect, it, vi } from 'vitest'
import { linkSummary, runLinkAction, shareAfterLinks, wouldExceed } from './venmoLinks'

describe('shareAfterLinks', () => {
  it('subtracts the reimbursed payments from the charge', () => {
    expect(shareAfterLinks(18000, [4500])).toBe(13500)
    expect(shareAfterLinks(18000, [4500, 4500])).toBe(9000)
  })
  it('never goes below zero', () => {
    expect(shareAfterLinks(10000, [10000])).toBe(0)
    expect(shareAfterLinks(10000, [6000, 6000])).toBe(0)
  })
  it('is the full charge with no reimbursements', () => {
    expect(shareAfterLinks(18000, [])).toBe(18000)
  })
})

describe('wouldExceed', () => {
  it('is false when the total lands exactly on the charge', () => {
    expect(wouldExceed(10000, [4000], 6000)).toBe(false)
  })
  it('is true one cent over the charge', () => {
    expect(wouldExceed(10000, [4000], 6001)).toBe(true)
  })
  it('treats an empty reimbursed list as nothing linked yet', () => {
    expect(wouldExceed(10000, [], 10000)).toBe(false)
    expect(wouldExceed(10000, [], 10001)).toBe(true)
  })
})

describe('linkSummary', () => {
  it('formats the remaining share against the charge', () => {
    expect(linkSummary(18000, [4500])).toBe('Your share: $135.00 of $180.00')
  })
  it('shows the full charge as the share with nothing linked', () => {
    expect(linkSummary(18000, [])).toBe('Your share: $180.00 of $180.00')
  })
  it('never shows a share below zero', () => {
    expect(linkSummary(10000, [6000, 6000])).toBe('Your share: $0.00 of $100.00')
  })
})

describe('runLinkAction', () => {
  it('reports the result via onSuccess and never calls onError or reload', async () => {
    const onSuccess = vi.fn()
    const onError = vi.fn()
    const reload = vi.fn()
    await runLinkAction(() => Promise.resolve('ok'), { onSuccess, onError, reload })
    expect(onSuccess).toHaveBeenCalledWith('ok')
    expect(onError).not.toHaveBeenCalled()
    expect(reload).not.toHaveBeenCalled()
  })

  it('regression: on a stale-row error (409/400/404), reports the error AND reloads, so a stale '
    + 'candidate/link row does not keep failing silently until the panel is reopened', async () => {
    const onSuccess = vi.fn()
    const onError = vi.fn()
    const reload = vi.fn()
    await runLinkAction(() => Promise.reject(new Error('This Venmo payment is already linked')), {
      onSuccess,
      onError,
      reload,
    })
    expect(onSuccess).not.toHaveBeenCalled()
    expect(onError).toHaveBeenCalledWith('This Venmo payment is already linked')
    expect(reload).toHaveBeenCalledTimes(1)
  })

  it('stringifies a non-Error rejection for onError', async () => {
    const onError = vi.fn()
    const reload = vi.fn()
    await runLinkAction(() => Promise.reject('boom'), { onSuccess: vi.fn(), onError, reload })
    expect(onError).toHaveBeenCalledWith('boom')
    expect(reload).toHaveBeenCalledTimes(1)
  })
})
