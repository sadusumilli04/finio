# Linking Venmo payments to Apple Card charges — Design

Date: 2026-09-21

## Goal

When you put a shared charge on your card and friends pay you back on Venmo, your real spending is the charge minus what came back. The user links the incoming Venmo payments to the card charge, and the app sets "my share" (the existing split field) to the charge minus the linked payments. The Dashboard and Insights already count the user's share, so they update without changes.

## Decisions

- **Manual linking first** (chosen by the user); suggested matches are a later step built on the same links.
- **One Venmo payment links to exactly one charge** (chosen by the user: friends pay back the whole amount except what the user owes). A charge can have several payments linked.
- **Storage:** a `venmo_links` table, one row per linked Venmo payment. Rejected: a column on `transactions` (a charge can have many payments) and a free-form note (cannot be recalculated or unlinked).
- **The share is derived:** on every link or unlink, `my_share = charge - sum(linked payments)` with `share_source = 'venmo'`. With no links left and `share_source = 'venmo'`, the share is cleared (the charge counts in full again).

## Rules

- **Charge side:** a `purchase` on an account whose source is not `venmo_csv`.
- **Payment side:** a `payment` (money in) on an account whose source is `venmo_csv`, not already linked to anything. The amount reimbursed is `abs(amount)`.
- **Too much:** linking is refused (400) when the linked total would exceed the charge (the share cannot go below $0).
- **Manual split:** linking when a manual share exists replaces it (the UI warns first). While a charge has links, editing its split by hand, or changing its amount or type, is refused with "Unlink the Venmo payments first" (400), so the share and links never disagree.
- **Errors:** a missing transaction is 404; a Venmo payment that is already linked is 409; a wrong kind of transaction on either side is 400.
- **Candidates:** for a charge dated D, the unlinked incoming Venmo payments dated from D - 3 days to D + 30 days, closest date first (then largest amount). The window is a named constant.
- **Deleting an account** deletes the links that involve its transactions (before its transactions), and recalculates the shares of card charges that lose links from another account being deleted.

## API

Under `/api/transactions/{id}`; amounts in cents; the two write calls return the updated charge (same shape as `GET /api/transactions` items).
- `GET /venmo-candidates` → `[{id, date, merchant, description, amount}]` (`amount` is the positive amount reimbursed).
- `GET /venmo-links` → the same item shape for the payments linked to this charge.
- `POST /venmo-links` body `{venmo_transaction_id}` → links, recalculates, returns the charge.
- `DELETE /venmo-links/{venmo_transaction_id}` → unlinks, recalculates, returns the charge.
- Transaction list items gain `venmo_link_count` (charges) and `venmo_linked_to` (the charge id, for a linked Venmo payment; otherwise null).

## UI (Transactions page)

- A charge's row menu gets **Link Venmo payments…**, which opens a panel beside the existing Split panel: the linked payments (each with Unlink), then the candidates (each with a Link button showing date, person, note, amount), and the resulting "Your share: $X of $Y".
- If the charge has a manual split, the panel says linking will replace it.
- A charge with links shows a small **Venmo-linked** tag; a linked Venmo payment shows **linked to <merchant>**. While a charge has links, the Split panel explains that the split comes from Venmo and how to change it.
- Errors show in the panel; no silent failures.

## Edge cases

- A payment whose amount is larger than the charge is refused; two payments that together exceed the charge, the second is refused.
- Unlinking the last payment restores the full charge; a manual share set before linking is not restored (it was replaced).
- Venmo payments that are not linked still count as money in (not spending), as today.
- The same Venmo payment cannot be linked twice.

## Testing

Backend (pytest): share maths for one and several links; every refusal (wrong side types, already linked, too much, manual edits and amount edits while linked); unlink restores; manual share replaced by linking; candidate window and ordering; list fields; account deletion cleaning links; the Dashboard total reflects the linked share. Frontend (Vitest) for pure helpers; the panel checked in a browser on a throwaway database. Docs: `docs/SPECIFICATION.md`, `docs/REQUIREMENTS.md`, `docs/TESTING.md`, README, CLAUDE.md invariants.

## Not in this step

Suggested matches, linking one Venmo payment to several charges, linking your outgoing Venmo payments to anything, and a Venmo balance view.
