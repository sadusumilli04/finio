# What the user actually spent on a transaction: their share when it is split, the whole charge otherwise.
# Defined once here so every query agrees. Queries must alias the transactions table as `t`.
EFFECTIVE_AMOUNT = "COALESCE(t.my_share, t.amount)"
