import { describe, expect, it } from 'vitest'
import { categoryColor, PALETTE } from './categoryColor'

describe('categoryColor', () => {
  it('is stable for a given category id', () => {
    expect(categoryColor(2, 'Grocery')).toBe(categoryColor(2, 'Grocery'))
  })

  it('gives the first categories clearly different colors', () => {
    const colors = Array.from({ length: PALETTE.length }, (_, i) => categoryColor(i + 1, 'Some category'))
    expect(new Set(colors).size).toBe(PALETTE.length)
  })

  it('wraps around once there are more categories than palette colors', () => {
    expect(categoryColor(PALETTE.length + 1, 'Extra')).toBe(categoryColor(1, 'First'))
  })

  it('uses a neutral grey for Other so uncategorized rows recede', () => {
    expect(categoryColor(4, 'Other')).toBe('#9aa3a0')
    expect(categoryColor(99, ' other ')).toBe('#9aa3a0')
  })

  it('never uses the neutral grey for a real category', () => {
    expect(PALETTE).not.toContain('#9aa3a0')
  })
})
