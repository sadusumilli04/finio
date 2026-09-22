import { describe, expect, it } from 'vitest'
import { linkSummary, shareAfterLinks, wouldExceed } from './venmoLinks'

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
