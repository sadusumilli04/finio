# Testing Finio

Thanks for trying this out. Finio is a private, local tool for analyzing Apple Card and Venmo spending — think of it like a personal, self-hosted Mint. This guide gets you looking at a working app in a couple of minutes, no coding required.

Everything you'll see is **fabricated sample data** — a made-up year of pretend purchases and Venmo payments, not anyone's real financial information.

## What you need

- **Docker Desktop**, installed and running. Get it free at [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/). That's the only thing you need to install — no Python, no Node.

## Start it up

Open a terminal in this folder and run:

```bash
docker compose up --build
```

The first run takes a minute or two while it builds. When you see something like `Uvicorn running on http://0.0.0.0:8000`, open your browser to:

**http://localhost:8000**

You should land on a Dashboard that's already full of a year's worth of sample spending — nothing more to set up.

## What to look at

- **Dashboard** — total spending, a category breakdown, a monthly trend, and top merchants. Try the date-range buttons and the category filter.
- **Insights** — pick different months from the dropdown. A few things were seeded on purpose so you have something to find:
  - A subscription (Netflix) that changes price partway through the year.
  - A month where a recurring gym charge is missing.
  - A merchant that only starts showing up partway through the year.
  - One unusually large purchase.
- **Transactions** — filter, search, recategorize a row, and try the ⋯ menu on a purchase:
  - **Split…** to say you only paid part of a charge.
  - **Link Venmo payments…** on a card charge to link the Venmo payments that reimbursed it (try it on a restaurant charge — there should be a Venmo payment nearby in the sample data).
  - **Make rule** to auto-categorize a merchant going forward.
- **Recurring** — the subscriptions and regular charges it's detected automatically.
- **Accounts** — see the two sample accounts (an Apple Card and a Venmo account). You can add another account here too.
- **Import** — if you want to see the import flow itself, the repo has a `testdata/` folder with the same two sample CSV files used to seed the app. Try importing one again — it should tell you the file was already imported.

## Starting over

Your changes (edits, splits, new accounts) are saved in a Docker volume, separate from anything on your own computer, so you can poke around freely. To wipe it and get a fresh copy of the sample data:

```bash
docker compose down -v
docker compose up --build
```

## Stopping

```bash
docker compose down
```

## Reporting what you find

Please don't use any real financial data while testing — sample data only. If something looks wrong or breaks, it's most useful to say:

1. What you did (which page, which button, what you typed).
2. What you expected to happen.
3. What actually happened (a screenshot or the exact error text helps a lot).
4. Your browser and OS.

Thanks for testing!
