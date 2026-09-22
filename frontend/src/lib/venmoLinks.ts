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

/**
 * Runs a link/unlink action. On success, hands the result to `onSuccess`. On failure (e.g. a 409/400/404
 * because the row went stale - already linked elsewhere, already unlinked, etc.), reports the error via
 * `onError` AND reloads via `reload`, so the panel doesn't keep showing a stale candidate/link row that
 * would otherwise just keep failing silently until the panel is reopened.
 */
export async function runLinkAction<T>(
  action: () => Promise<T>,
  handlers: { onSuccess: (result: T) => void; onError: (message: string) => void; reload: () => void },
): Promise<void> {
  try {
    const result = await action()
    handlers.onSuccess(result)
  } catch (err) {
    handlers.onError(err instanceof Error ? err.message : String(err))
    handlers.reload()
  }
}
