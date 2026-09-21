# Split transactions ("my share") — Design

Date: 2026-09-20

## Goal

Let the user record how much of a charge was actually theirs. In a group dinner one person often puts the whole bill on their card and is paid back; the full charge should not count as that person's spending. Only the user's share counts. Venmo integration will come later, so the design leaves a place for it to attach.

## Decisions

- **Model:** an optional `my_share` amount on each transaction (approach A). A separate splits table (per-person rows) and overwriting the charge amount were considered and rejected: the first is more than is needed now and can be added later beside this; the second would make the app stop matching the card statement and could disturb duplicate detection.
- **The rest of the charge:** simply left out of spending. There is no tracking of who owes what.
- **Default:** every transaction is unsplit. Importing never sets a split, and re-importing an overlapping statement keeps existing splits (rows already stored are skipped). The user opts in per transaction.
- **Entry:** an exact dollar amount, plus a shortcut that splits evenly among N people and fills the amount in. No percentage input.
- **Out of scope:** Venmo itself, per-person amounts, tracking outstanding money owed, percentage entry.

## Data model

Two nullable columns are added to `transactions`:

- `my_share INTEGER` — cents, `CHECK (my_share IS NULL OR my_share >= 0)`. `NULL` means the whole charge is the user's.
- `share_source TEXT` — `CHECK (share_source IS NULL OR share_source IN ('manual', 'venmo'))`. `'manual'` when the user entered the share; `'venmo'` is reserved for the future Venmo importer. Both columns are `NULL` together or set together.

The original `amount` is never modified, so the app keeps matching the statement.

**Effective amount.** "What the user spent" on a transaction is `COALESCE(my_share, amount)`. It is defined once, as a SQL constant in a single module (`backend/finio/services/amounts.py`, `EFFECTIVE_AMOUNT = "COALESCE(t.my_share, t.amount)"`), and every query that needs it imports that constant. The API also returns it as `effective_amount` so clients never repeat the rule.

**Migration.** `PRAGMA user_version` moves from 1 to 2. `init_db` creates the full schema (new columns included) for fresh databases; for an existing database it checks `PRAGMA table_info(transactions)` and runs `ALTER TABLE transactions ADD COLUMN ...` for any missing column, then raises `user_version` to 2 (never lowers it). Existing rows keep `NULL` in both columns, so nothing changes for them. The check is by column presence, so it also works for databases stamped 0 or 1.

## Rules

- Only transactions with `type = 'purchase'` can be split. Payments, refunds, income and other types are rejected with a validation error (400).
- `my_share` must satisfy `0 <= my_share <= amount`. `0` is allowed (someone else fully covered the charge). Anything else is rejected (400).
- Sending `my_share: null` removes the split and clears `share_source`.
- Setting a share sets `share_source = 'manual'`.
- Imported transactions remain read-only except for `category_id` and now `my_share`; both are annotations the user adds.
- Editing a **manual** transaction that has a split: if the new amount is lower than `my_share` the edit is rejected (400, "split exceeds the new charge; edit the split first"); changing its direction to income or refund clears the split.
- Rules ("Make rule"), re-applying rules, and re-importing never touch `my_share`.
- Deleting an account deletes its transactions and therefore their splits (unchanged behaviour).

## API

- `PATCH /api/transactions/{id}` accepts `my_share` (integer cents or `null`). For imported rows the allowed fields are `category_id` and `my_share`. Unlike the other fields, an explicit `null` is valid for `my_share`.
- `POST /api/transactions` (manual entry) does not take `my_share`: new transactions are always unsplit, and the user splits afterwards from the row menu.
- Every transaction object gains `my_share` (cents or null), `share_source`, and `effective_amount` (cents).
- `GET /api/transactions`: `sort=amount`, `min_amount` and `max_amount` operate on `effective_amount`. The default sort and all other filters are unchanged.
- The analytics endpoints keep their shapes; their numbers change meaning (below).

## Spending semantics

"Spending" already means purchases only. It now means the **effective amount** of purchases. This applies to spending by category, monthly trends (and therefore the median line), top merchants, and recurring-charge detection (its amount-similarity check uses effective amounts). Purchases whose effective amount is `0` are excluded from these analytics, so a fully repaid dinner leaves no `$0` row, category entry or empty pie slice; such transactions remain in the transaction list.

## UI

**Row menu.** A purchase's ⋯ menu gets **Split…**. A split transaction's menu shows **Edit split…** and **Remove split** instead. Non-purchases show neither.

**Split panel.** Opens above the table, like the Add/Edit transaction form:

```
Split "Home Plate"                                    Charge: $120.00
Split evenly among [ 4 ] people  [Fill in]
My share ($)  [ 30.00 ]                       Paid for others: $90.00
                                          [Save split]  [Cancel]
```

- **Fill in** sets My share to `charge / N` rounded to the nearest cent (for example $100 among 3 gives $33.33). N must be a whole number of at least 2. The user can then edit the number.
- **Paid for others** is `charge - My share` and updates as the user types.
- Validation is inline: the amount must be a valid dollar amount between $0.00 and the charge, and $0.00 is accepted (the existing amount parser rejects zero, so this uses its own zero-allowing parse).
- **Remove split** appears when editing an existing split.

**Table.** A split row shows the user's share in bold with the full charge beneath it in small muted text ("of $120.00"). Unsplit rows look exactly as they do today. The amount column, and the sort and amount filters, use the effective amount.

**Dashboard.** No new controls; the numbers reflect the user's share.

## Venmo, later

A Venmo importer would call the same service function the manual split uses (set share on a transaction with `share_source = 'venmo'`); no reader changes, because every consumer already reads the effective amount. If per-friend detail is wanted later, a splits table can be added beside `my_share` without changing the totals code.

## Testing

Backend (pytest):
- Migration: a hand-built version-1 database gains both columns with data preserved and version 2; a fresh database is version 2; running init twice is harmless; a database stamped 0 with the old schema also migrates.
- Validation and permissions: split allowed on imported and manual purchases; rejected on payment/refund/income; rejected when negative or above the charge; `0` accepted; `null` clears; `share_source` set to `manual`; other fields on an imported row still 403; manual edit rules (amount below share rejected, direction change clears).
- Analytics: category totals, trends, top merchants and recurring use the share; a `$0` share disappears from analytics but stays in the list; unsplit data behaves exactly as before.
- Transaction list: `effective_amount` returned; sort and min/max amount use it.
- Re-import keeps existing splits.

Frontend (Vitest): even-split rounding and input rules, the zero-allowing share parser, and the split validation (over the charge, blank, invalid). The screens are checked in a browser against fabricated data on a throwaway database.

## Docs to update

`docs/SPECIFICATION.md` (data model, spending semantics, API, UI), `docs/REQUIREMENTS.md` (new requirements for splitting), and the README "Use" section.
