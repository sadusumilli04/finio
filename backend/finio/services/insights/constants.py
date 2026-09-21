"""Every threshold the Insights page uses. Amounts are cents. Tune them here."""

MOVER_MIN_CHANGE = 1000            # ignore category changes under $10
MOVERS_PER_SIDE = 3

NEW_MERCHANTS_LIMIT = 10

GROWING_MIN_CHANGE = 2500          # a merchant grew by at least $25 ...
GROWING_MIN_RATIO = 1.5            # ... and to at least 1.5x last time
GROWING_LIMIT = 5

UNUSUAL_MIN_HISTORY = 5            # earlier purchases needed in the category
UNUSUAL_RATIO = 3                  # at least 3x the category's typical charge ...
UNUSUAL_MIN_AMOUNT = 5000          # ... and at least $50
UNUSUAL_LIMIT = 5

SUBSCRIPTION_MIN_PCT = 5           # a price change of at least 5% ...
SUBSCRIPTION_MIN_CHANGE = 100      # ... and at least $1
SUBSCRIPTION_NEW_MONTHS = 3        # "new" = first charge within the 3 months ending with the selected one
SUBSCRIPTION_MISSING_GRACE_DAYS = 5

PROJECTION_MIN_DAYS = 7            # project a month-end total from day 7 on
TYPICAL_MIN_MONTHS = 3             # other complete months needed for a "typical month" and a rank
