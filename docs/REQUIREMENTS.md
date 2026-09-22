# Finio requirements

The requirements gathered while designing Finio. `SPECIFICATION.md` covers how they are met; this file covers what the app must do and the constraints it works within.

## Purpose

An app for analyzing my Apple Card transactions, similar to what Mint used to do. It may support transactions from other accounts later.

## Platform and privacy

- **R1.** Runs as a local web app on my Mac: a backend plus a browser UI at localhost.
- **R2.** All data is stored locally in a SQLite file. Financial data never leaves the machine.
- **R3.** Core logic (import, categorization, analysis) sits behind an API, so a native Apple app can reuse it later and the browser UI is only one client.
- **R4.** Stack: Python (FastAPI) backend, React + TypeScript frontend, SQLite.

## Getting transactions in

- **R5.** Apple Card transactions come from the CSV export of a monthly statement. Apple has no API, so there is no automatic sync.
- **R6.** The importer reads Apple's real export format: `Transaction Date`, `Clearing Date`, `Description`, `Merchant`, `Category`, `Type`, `Amount (USD)`, `Purchased By`.
- **R7.** Overlapping exports must not create duplicates. Apple's CSV has no transaction ID, so rows are matched by a fingerprint, and two genuinely identical same-day purchases must both be kept.
- **R8.** Importing the exact same file twice is rejected.
- **R9.** Each import reports how many rows were added, how many were skipped as duplicates, and how many had an unrecognized type. Rows that can't be read are reported with their line numbers and skipped without failing the whole file.
- **R10.** Payments and refunds are recognized and stored as money in, not spending. The original CSV row is kept on every imported transaction.
- **R11.** Other accounts are supported through manual entry: I can create an account and add transactions by hand (see Manual entry). PDF import is not needed.
- **R12.** New sources should be easy to add later, as a new importer for a new account type.

## Categories and rules

- **R13.** I have my own set of categories, seeded from Apple's (Entertainment, Grocery, Insurance, Other, Restaurants, Shopping, Transportation, Utilities). I can add and rename categories, except that `Other` stays. If an imported row has a category that isn't in my set, that category is added and the row keeps it; `Other` is only for rows that have no category at all.
- **R14.** I can recategorize any transaction, and I can create a rule such as "merchant contains Target -> Grocery" that applies to future imports and can be re-applied to existing transactions.
- **R15.** A category I set by hand is never overwritten by a rule.
- **R16.** Messy merchant names (extra whitespace, prefixes like `SQ *`) are cleaned up, with user-defined aliases, so search, rules, and recurring detection work on clean names.

## Manual entry

- **R17.** For accounts with no importer, I can add a transaction with an account, date, amount, direction (expense, income, or refund), merchant, and a category I pick. Description and cardholder are optional.
- **R18.** The form validates inline: the amount must be greater than zero, the date and merchant are required, and the category must be chosen.
- **R19.** The form remembers my last account and date and autocompletes merchants from ones I've used.
- **R20.** Manual transactions can be edited and deleted. Imported transactions can only be recategorized (and split, see R32).
- **R21.** Manual transactions count in all analytics, filters, and recurring detection.

## Analysis (v1 features)

- **R22.** Spending by category over time: category totals, monthly trends, and top merchants (at my share, R32).
- **R23.** Search and filter transactions by date, merchant, category, amount, account, and cardholder, with sorting and paging, plus inline recategorizing.
- **R24.** Recurring charges and subscriptions: detected automatically from repeating merchants (weekly, biweekly, monthly, yearly) with the typical amount and next expected date (amounts at my share, R32).
- **R25.** Accounts and balances: the account model stores balances (a starting balance and date), so a net-worth view can be added once there is more than one account.
- **R26.** "Spending" counts purchases only, at my share when a purchase is split (R32). A purchase whose share is $0 is left out of spending totals, charts, top merchants, and recurring detection, but stays in the transaction list. Payments, refunds, and income are excluded.
- **R27.** The card is shared by more than one person, so cardholder (`Purchased By`) can be filtered on every screen.

## Splitting a charge

- **R32.** A transaction can be split so that only my share counts as spending, for example when I put a group dinner on my card and am paid back.
- **R33.** Transactions start unsplit; I opt in per transaction, and importing never sets a split.
- **R34.** I enter the split as an exact amount, with a shortcut that splits evenly among N people and fills the amount in.
- **R35.** The original charge stays intact and visible, so the app keeps matching the card statement.
- **R36.** Venmo reimbursements can be matched to charges to set the share (see Linking Venmo payments to charges, R56-R61).
- **R37.** Top merchants on the Dashboard: I can choose how many to show (5, 10, 25 or 50) and rank them by most spent or by most visits.
- **R38.** The Dashboard can be filtered by category, in addition to date range, cardholder and account.

## Insights

- **R39.** An Insights page, opened from the top navigation, tells me month by month what stands out in my spending. A month picker lists the months that have spending, with previous/next arrows; it opens on the current month, or the latest month with spending if the current one has none.
- **R40.** A month summary shows the total, the change against the previous month, my typical month (needs at least 3 other complete months), the month's rank among complete months, and for an in-progress month a projected month-end total (from day 7). An in-progress month is compared only with the same days of the previous month.
- **R41.** Biggest movers: the categories that went up and down the most against the previous month (changes under $10 ignored).
- **R42.** New merchants: merchants I had never spent at before this month.
- **R43.** Merchants that grew: merchants whose spending rose by at least $25 and 1.5x against the previous month.
- **R44.** Unusual charges: purchases far above what is typical for their category (at least 3x the category median and $50, with enough history).
- **R45.** Subscription changes: monthly recurring charges whose price went up or down, that are new, or that look missing.
- **R46.** Insights count only my share of split purchases and leave out $0 shares, like all other spending (R26).
- **R47.** A Person filter on Insights ("Everyone" or one cardholder) limits every insight, the month list, the typical month and the rank to that person's spending. Changing the person keeps the selected month if that person has spending in it, otherwise it jumps to their latest month.

## Venmo

- **R48.** I can import a Venmo account statement CSV into a Venmo account (source "Venmo CSV import"), through the same Accounts and Import pages. The statement's title, balance, footer and disclaimer rows are ignored; a file that is not a Venmo statement is rejected with a clear error.
- **R49.** Money I send (a payment, or a charge I pay) is spending, at my share if I split it (R26, R32).
- **R50.** Money I receive is money in, not spending, and does not reduce spending.
- **R51.** Transfers to my bank (`Standard Transfer`, `Instant Transfer`) are not transactions of mine and are skipped on import: they are never stored and never counted, in `rows_total` or anywhere else.
- **R52.** Importing is duplicate-safe by Venmo transaction ID: overlapping statements skip rows already stored, and a repeated ID inside one file is skipped. Importing the exact same file twice is still rejected (R8).
- **R53.** Only completed rows (`Complete`, `Issued`) are imported. Pending, cancelled or failed rows are reported as row errors and are never counted as spending.
- **R54.** Venmo payments and charges default to a new **Friends & Family** category.
- **R55.** Category rules (matching the counterparty or the note) and splits work on Venmo rows like any other.

## Linking Venmo payments to charges

- **R56.** I can link an incoming Venmo payment (money in, on a Venmo account) to a card charge (a purchase on a non-Venmo account) from the charge's row menu. A Venmo payment links to exactly one charge; a charge can have several linked payments.
- **R57.** Linking or unlinking recalculates my share as the charge minus the total of what's linked, recorded with `share_source` "venmo". Unlinking the last payment restores the full charge as unsplit; a manual share set before linking is not restored, since linking replaced it.
- **R58.** Linking is refused when the linked total would exceed the charge, when either side is the wrong kind of transaction, when the transaction doesn't exist, or when the Venmo payment is already linked to another charge.
- **R59.** Linking a charge that already has a manual split replaces it, and the app warns before doing so. While a charge has links, editing its split by hand, or changing its amount or direction, is refused until the payments are unlinked, so the recorded links and the share never disagree.
- **R60.** For a given charge, I'm shown unlinked incoming Venmo payments dated within a window around the charge's date as candidates to link, closest date first, then largest amount.
- **R61.** Deleting an account removes the links involving its transactions, and recalculates the share of any card charge that loses a link because the other side's account was deleted.

## Trying it out

- **R62.** A one-command Docker quick start (`docker compose up --build`) runs the whole app from one container on one port, with no Python or Node install needed.
- **R63.** That container starts pre-seeded with a year of fabricated sample data, so there's something to look at immediately; it never re-seeds or duplicates data once any account exists, including across a container restart.
- **R64.** The Docker packaging changes nothing about local development: the seeding and the single-origin static serving only activate inside the Docker image.

## Screens

- **R28.** Dashboard, Insights, Transactions, Recurring, Import, and Accounts.

## Quality and process

- **R29.** Amounts are stored as integer cents; dates as ISO `YYYY-MM-DD`.
- **R30.** Tests: pytest for the backend, Vitest for frontend logic, written test first. Fixtures use fabricated rows only.
- **R31.** Real statements are never committed to the repository.

## Out of scope for v1

Budgets, a net-worth view, suggested (automatic) Venmo-to-charge matches, linking one Venmo payment to several charges, linking outgoing Venmo payments to anything, a Venmo balance view, offsetting spending with money received, per-person split amounts, tracking money owed, PDF import, Plaid or other aggregator sync, auth and hosting, a native Apple app, and screens for managing categories and merchant aliases (these are available through the API).
