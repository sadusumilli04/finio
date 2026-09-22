# Venmo CSV import — Design

Date: 2026-09-21

## Goal

Import Venmo account statements (CSV) and treat them like the Apple Card CSV: duplicate-safe imports, categories and rules, the Transactions page, splits, and the Dashboard and Insights. A Venmo account is created and imported through the same Accounts and Import pages.

## Decisions

- **Money semantics** (chosen by the user): money you send counts as spending, money you receive is "money in", and transfers to your bank are ignored. Automatically offsetting spending with money received, and matching a Venmo reimbursement to an Apple Card charge (`share_source = 'venmo'`), are **later** work.
- **Default category** (chosen by the user): a new **Friends & Family** category. Rules and manual choices override it as for any source.
- **Architecture:** one new importer class registered in `IMPORTERS` (`services/ingestion.py`), the pattern the Apple importer already follows. Ingestion, dedup, rules, transactions, analytics and insights are not changed except where noted below. Rejected: a separate Venmo module or table (duplicates every feature) and treating Venmo as manual entry (no import, no dedup).
- **Real data never enters the repo.** The user's example statement was shared in chat only. Test fixtures are fabricated files in the same shape.

## The Venmo statement

Header rows come first: a title row (`Account Statement - (@username)`), an `Account Activity` row, the column header row, then a balance row (only a Beginning Balance value). Transaction rows follow, each with a leading empty column, then a footer row (ending balance, fees) and a long legal disclaimer in one quoted, multi-line cell. Relevant columns: `ID`, `Datetime` (ISO, `2026-09-10T00:53:22`), `Type`, `Status`, `Note`, `From`, `To`, `Amount (total)` (signed from the account holder's point of view, written like `- $20.00` or `+ $56.52`, sometimes with thousands separators), `Funding Source`, `Destination`. The whole row is kept in `raw_row`.

## Row mapping

| Venmo row | `type` | `amount` (cents) | Notes |
|---|---|---|---|
| `Payment` or `Charge` with amount `- $X` (you pay) | `purchase` | `+X` | counts as spending |
| `Payment` or `Charge` with amount `+ $X` (you receive) | `payment` | `-X` | money in, not spending |
| `Standard Transfer` (and `Instant Transfer`) | `transfer` | `+X` if sent out, otherwise `-X` | not spending, kept for the record |
| Anything else | `other`, flagged | by sign | shown in the import summary, as with Apple |

- **Merchant:** the counterparty. In a `Payment` row `From` is the payer and `To` the payee; in a `Charge` row `From` is the requester and `To` the person charged. So the counterparty is `To` for a Payment you pay, `From` for a Payment you receive, `From` for a Charge you pay, and `To` for a Charge you receive. Transfers use `Venmo transfer` as the merchant.
- **Description** (`raw_description`): the note (`Venmo payment`, `Venmo charge` or the transfer type when the note is blank). Rules that match on description or merchant work, so a rule such as "bjs → Grocery" applies.
- **Category:** `source_category = "Friends & Family"` for payments and charges, so the existing behaviour for an unknown source category creates and assigns it. Transfers use `Other`.
- **Dates:** `transaction_date` is the date part of `Datetime`. There is no posted date.
- **Cardholder:** none.
- **Status:** rows with a status other than `Complete` or `Issued` (for example `Pending`, `Cancelled`, `Failed`) are not imported and are reported as row errors ("status: X"), so they are not counted as spending.
- The `Amount (total)` sign, not the `From`/`To` names, decides the direction, because the user's own name in the statement is not otherwise known.

## Duplicates

Venmo rows have a unique `ID`. `RawTransaction` gets an optional `external_id`; `fingerprint()` in `services/dedup.py` uses `account_id` and `external_id` when it is present and keeps the existing recipe otherwise, so Apple dedup is unchanged. Overlapping statements skip rows already seen; identical files are still rejected by hash. Two rows with the same ID inside one file are treated as duplicates of each other (the second is skipped).

## Accounts and UI

- New account source `venmo_csv` (API literal in `api/accounts.py`, the `AccountSource` type and the Accounts page dropdown "Venmo CSV import"); the account type stays `other`. The label in the Accounts table becomes "Venmo CSV import".
- The Import page needs no change beyond listing the new account.
- The Dashboard and Insights need no change. Venmo purchases count at the user's share like any other, and transfers and money in are excluded by the existing rule that spending is `type = 'purchase'`.

## Errors

- A file without the Venmo column header is rejected with `Not a Venmo CSV; missing columns: [...]` (a 400 through `ValidationFailed`, as for Apple).
- The title row, blank row, balance row, footer row and the disclaimer are skipped silently; they have no `ID`/`Datetime`.
- A row with a bad date or amount is reported in the error list without stopping the import.

## Edge cases

- A payment and its return (a Venmo note on an ordinary Payment row, not a Venmo type) on the same day do not cancel; both are kept (one spending, one money in).
- Amounts are integer cents from decimal parsing; `$1,250.00` is handled.
- A file where the user is charged by a friend (`Charge`, `- $9.00`) is spending, the same as a payment.

## Testing

Backend (pytest), with a fabricated `backend/tests/fixtures/venmo_sample.csv`: each row kind and its sign, the amount formats, the footer and disclaimer being skipped, the wrong-file error, non-final statuses, dedup across overlapping files and inside one file, the account source through the API, an import through the API that creates the category, and rules matching on the note. Existing Apple tests stay unchanged and green. Frontend: `tsc` only (a type and a dropdown option). Docs to update: `docs/SPECIFICATION.md`, `docs/REQUIREMENTS.md`, `docs/TESTING.md`, the README and the CLAUDE.md importer line.

## Not in this step

Matching Venmo reimbursements to Apple Card charges, offsetting spending with money received, Venmo balance tracking, and per-person Venmo views.
