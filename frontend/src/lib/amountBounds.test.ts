import { describe, expect, it } from 'vitest'
import { amountBounds } from './amountBounds'

describe('amountBounds', () => {
  it('treats blank as no bound', () => {
    expect(amountBounds('', '  ')).toEqual({})
  })
  it('converts valid values to cents', () => {
    expect(amountBounds('5', '12.50')).toEqual({ min: 500, max: 1250 })
    expect(amountBounds('', '$1,000')).toEqual({ max: 100000 })
  })
  it('reports unparseable values and drops that bound', () => {
    expect(amountBounds('abc', '10')).toEqual({ max: 1000, minError: 'Enter an amount like 12.50' })
    expect(amountBounds('1', 'x')).toEqual({ min: 100, maxError: 'Enter an amount like 12.50' })
  })
  it('errors when min exceeds max', () => {
    expect(amountBounds('20', '10')).toEqual({ rangeError: 'Min amount is greater than max amount' })
  })
})
