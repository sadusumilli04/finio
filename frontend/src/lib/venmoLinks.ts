import { formatCents } from './money'

/** What the charge still costs after the linked Venmo payments reimburse part of it; never below zero. */
export function shareAfterLinks(charge: number, reimbursed: number[]): number {
  const total = reimbursed.reduce((sum, n) => sum + n, 0)
  return Math.max(0, charge - total)
}

/** Whether linking one more payment (`next`) on top of what's already reimbursed would exceed the charge. */
export function wouldExceed(charge: number, reimbursed: number[], next: number): boolean {
  const total = reimbursed.reduce((sum, n) => sum + n, 0)
  return total + next > charge
}

export function linkSummary(charge: number, reimbursed: number[]): string {
  return `Your share: ${formatCents(shareAfterLinks(charge, reimbursed))} of ${formatCents(charge)}`
}
