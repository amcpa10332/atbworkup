"""
Financial-statement category for tax lines — the single source of truth for
"which GAAP bucket does this line belong to" (Revenue, COGS, Operating
Expense, Schedule K, Current Asset, Fixed Asset, ...), independent of the
line's section display name (which a preparer can rename) or its account's
debit/credit sign (which only tells you increase-vs-decrease, not category).

Every tax line is classified ONCE here, at template-seed time, and the
category is stored on the tax_line row itself. Downstream calculations
(gross profit, net income, Schedule K breakouts, GAAP-style report
subtotals) read this stored field instead of pattern-matching section names
at runtime — that pattern-matching was the root cause of several
consolidation math bugs (see session history): a renamed or non-standard
section string silently fell through the cracks.

Categories:
    revenue              — increases income; shown positive in P&L reporting
    cogs                 — decreases income; subtotaled into Gross Profit
    opex                 — decreases income (operating expenses / deductions)
    distribution         — distributions to owners/beneficiaries (trusts,
                           etc.); not an expense, but reduces distributable
                           income
    schedule_k           — pass-through items (1065/1120S); mixes income-
                           and deduction-type accounts, so callers must use
                           each account's own normal_balance, not a blind
                           section sum
    current_asset        — Balance Sheet: cash, AR, inventory, prepaids...
    fixed_asset          — Balance Sheet: PP&E, intangibles
    other_asset          — Balance Sheet: anything not clearly current/fixed
                           (long-term investments, deposits, loans made...)
    current_liability     — Balance Sheet: AP, accrued expenses, current
                           portion of long-term debt...
    noncurrent_liability  — Balance Sheet: long-term debt, mortgages...
    equity               — Balance Sheet: capital, retained earnings, draws
    ""                   — unclassified (legacy/custom line with no mapping)
"""
from __future__ import annotations

CATEGORY_REVENUE      = "revenue"
CATEGORY_COGS         = "cogs"
CATEGORY_OPEX         = "opex"
CATEGORY_DISTRIBUTION = "distribution"
CATEGORY_SCHEDULE_K   = "schedule_k"

CATEGORY_CURRENT_ASSET       = "current_asset"
CATEGORY_FIXED_ASSET         = "fixed_asset"
CATEGORY_OTHER_ASSET         = "other_asset"
CATEGORY_CURRENT_LIABILITY    = "current_liability"
CATEGORY_NONCURRENT_LIABILITY = "noncurrent_liability"
CATEGORY_EQUITY               = "equity"

# Older, coarser values — no longer produced by classify_section(), but kept
# so a migration can recognize "this tax line predates the current_asset /
# fixed_asset / other_asset split" and re-derive it (see models/job.py).
_LEGACY_CATEGORY_ASSET     = "asset"
_LEGACY_CATEGORY_LIABILITY = "liability"
LEGACY_COARSE_CATEGORIES = {_LEGACY_CATEGORY_ASSET, _LEGACY_CATEGORY_LIABILITY}

ASSET_CATEGORIES = {CATEGORY_CURRENT_ASSET, CATEGORY_FIXED_ASSET, CATEGORY_OTHER_ASSET}
LIABILITY_CATEGORIES = {CATEGORY_CURRENT_LIABILITY, CATEGORY_NONCURRENT_LIABILITY}

# Sections whose net-income contribution must be computed per-account (raw
# DR/CR), never by blindly summing the section's display total.
MIXED_SIGN_CATEGORIES = {CATEGORY_SCHEDULE_K}

# Categories that roll into Gross Profit (Revenue - COGS).
GROSS_PROFIT_CATEGORIES = {CATEGORY_REVENUE, CATEGORY_COGS}

# Display order + label for each GAAP Balance Sheet subtotal bucket.
ASSET_BUCKET_ORDER = [
    (CATEGORY_CURRENT_ASSET, "Total Current Assets"),
    (CATEGORY_FIXED_ASSET, "Total Fixed Assets"),
    (CATEGORY_OTHER_ASSET, "Total Other Long-Term Assets"),
]
LIABILITY_BUCKET_ORDER = [
    (CATEGORY_CURRENT_LIABILITY, "Total Current Liabilities"),
    (CATEGORY_NONCURRENT_LIABILITY, "Total Noncurrent Liabilities"),
]


def classify_section(financial_statement: str, section: str) -> str:
    """Best-effort classification from (financial_statement, section) —
    used to populate the stored category at template-seed time, and as a
    fallback for legacy tax lines saved before the category column existed."""
    s = (section or "").strip().lower()

    if financial_statement == "BalanceSheet":
        if "current" in s and "liab" in s:
            return CATEGORY_CURRENT_LIABILITY
        if "liab" in s:
            # "Long-Term Liabilities" / bare "Liabilities" with no current/
            # long-term qualifier — treat unqualified liabilities as current
            # (conservative default: assume due sooner, not later).
            return (CATEGORY_NONCURRENT_LIABILITY
                    if any(k in s for k in ("long", "noncurrent", "long-term"))
                    else CATEGORY_CURRENT_LIABILITY)
        if any(k in s for k in (
            "equity", "capital", "net assets", "corpus", "stockholders", "shareholders",
        )):
            return CATEGORY_EQUITY
        if "current" in s:
            return CATEGORY_CURRENT_ASSET
        if "fixed" in s or "intangible" in s:
            return CATEGORY_FIXED_ASSET
        return CATEGORY_OTHER_ASSET

    # ProfitAndLoss (and anything else not explicitly BalanceSheet)
    if "schedule k" in s:
        return CATEGORY_SCHEDULE_K
    if "cost of goods" in s or s == "cogs":
        return CATEGORY_COGS
    if "distribution" in s:
        return CATEGORY_DISTRIBUTION
    if "disbursement" not in s and any(
        k in s for k in ("revenue", "income", "receipts")
    ):
        return CATEGORY_REVENUE
    return CATEGORY_OPEX
