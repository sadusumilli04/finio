import { describe, expect, it } from 'vitest'
import { median } from './stats'

describe('median', () => {
  it('returns null when there is nothing to average', () => {
    expect(median([])).toBeNull()
  })

  it('picks the middle value of an odd count, regardless of input order', () => {
    expect(median([300, 100, 200])).toBe(200)
    expect(median([500])).toBe(500)
  })

  it('averages the two middle values of an even count, rounded to a whole cent', () => {
    expect(median([100, 200, 300, 400])).toBe(250)
    expect(median([1, 2])).toBe(2) // 1.5 rounds to 2
    expect(median([100000, 250000])).toBe(175000)
  })

  it('does not mutate its input', () => {
    const values = [3, 1, 2]
    median(values)
    expect(values).toEqual([3, 1, 2])
  })
})
