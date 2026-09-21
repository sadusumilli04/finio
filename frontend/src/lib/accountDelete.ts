export function deleteAccountPrompt(name: string, transactionCount: number): string {
  if (transactionCount === 0) return `Delete account "${name}"?`
  const noun = transactionCount === 1 ? 'transaction' : 'transactions'
  return `Delete account "${name}" and its ${transactionCount.toLocaleString('en-US')} ${noun} and import history? This cannot be undone.`
}
