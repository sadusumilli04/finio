from finio.services.amounts import EFFECTIVE_AMOUNT


def where_clause(
    *,
    date_from=None,
    date_to=None,
    account_id=None,
    cardholder=None,
    category_id=None,
    merchant=None,
    min_amount=None,
    max_amount=None,
    q=None,
) -> tuple[str, list]:
    conds: list[str] = []
    params: list = []

    def add(cond: str, *values):
        conds.append(cond)
        params.extend(values)

    if date_from:
        add("t.transaction_date >= ?", str(date_from))
    if date_to:
        add("t.transaction_date <= ?", str(date_to))
    if account_id is not None:
        add("t.account_id = ?", account_id)
    if cardholder:
        add("t.cardholder = ?", cardholder)
    if category_id is not None:
        add("t.category_id = ?", category_id)
    if merchant:
        add("lower(t.merchant_clean) LIKE ?", f"%{merchant.lower()}%")
    if min_amount is not None:
        add(f"{EFFECTIVE_AMOUNT} >= ?", min_amount)
    if max_amount is not None:
        add(f"{EFFECTIVE_AMOUNT} <= ?", max_amount)
    if q:
        like = f"%{q.lower()}%"
        add("(lower(t.merchant_clean) LIKE ? OR lower(t.raw_description) LIKE ?)", like, like)
    return (" AND ".join(conds) if conds else "1=1"), params
