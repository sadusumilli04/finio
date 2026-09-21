import { describe, expect, it } from 'vitest'
import { deleteAccountPrompt } from './accountDelete'

describe('deleteAccountPrompt', () => {
  it('asks a plain question for an empty account', () => {
    expect(deleteAccountPrompt('Chase', 0)).toBe('Delete account "Chase"?')
  })

  it('states how many transactions will be removed, singular and plural', () => {
    expect(deleteAccountPrompt('Apple Card', 1)).toBe(
      'Delete account "Apple Card" and its 1 transaction and import history? This cannot be undone.',
    )
    expect(deleteAccountPrompt('Apple Card', 1234)).toBe(
      'Delete account "Apple Card" and its 1,234 transactions and import history? This cannot be undone.',
    )
  })
})
