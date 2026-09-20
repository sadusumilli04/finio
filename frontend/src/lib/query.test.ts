import { describe, expect, it } from 'vitest'
import { toQueryString } from './query'

describe('toQueryString', () => {
  it('returns empty string when nothing is set', () => {
    expect(toQueryString({})).toBe('')
    expect(toQueryString({ a: undefined, b: null, c: '' })).toBe('')
  })
  it('encodes set values', () => {
    expect(toQueryString({ q: 'a b', limit: 50, skip: undefined })).toBe('?q=a+b&limit=50')
  })
  it('keeps zero', () => {
    expect(toQueryString({ offset: 0 })).toBe('?offset=0')
  })
})
