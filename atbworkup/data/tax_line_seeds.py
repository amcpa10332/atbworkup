"""
IRS-accurate tax line seed data for all supported entity types.

Each tuple: (entity_type, financial_statement, section, section_sort_order,
             line_code, line_name, sort_order)

Line codes mirror the actual form line references so preparers can trace them
to the face of the return, Schedule K, and Schedule L:
  - Schedule L asset/liability lines: "L-1", "L-2a", etc.
  - Page 1 income/deduction lines:   "1a", "7", "19", etc.
  - Schedule K items:                "K-2", "K-4", etc.

Verify against current-year forms — IRS may renumber lines in any given year.
"""

# (entity_type, financial_statement, section, section_sort_order,
#  line_code, line_name, sort_order)
DEFAULT_TAX_LINES: list[tuple] = [

    # ══════════════════════════════════════════════════════════════════════
    # FORM 1120-S  (S-Corporation)
    # Balance Sheet = Schedule L
    # Income Statement = Page 1 + Schedule K pass-through items
    # ══════════════════════════════════════════════════════════════════════

    # ── Schedule L — Assets ───────────────────────────────────────────────
    ("1120S", "BalanceSheet", "Current Assets",              10, "L-1",   "Cash",                                        10),
    ("1120S", "BalanceSheet", "Current Assets",              10, "L-2a",  "Trade Notes & Accounts Receivable",           20),
    ("1120S", "BalanceSheet", "Current Assets",              10, "L-2b",  "Less: Allowance for Bad Debts",               30),
    ("1120S", "BalanceSheet", "Current Assets",              10, "L-3",   "Inventories",                                 40),
    ("1120S", "BalanceSheet", "Current Assets",              10, "L-4",   "U.S. Government Obligations",                 50),
    ("1120S", "BalanceSheet", "Current Assets",              10, "L-5",   "Tax-Exempt Securities",                       60),
    ("1120S", "BalanceSheet", "Current Assets",              10, "L-6",   "Other Current Assets",                        70),
    ("1120S", "BalanceSheet", "Loans & Other Investments",   20, "L-7",   "Loans to Shareholders",                       10),
    ("1120S", "BalanceSheet", "Loans & Other Investments",   20, "L-8a",  "Mortgage & Real Estate Loans",                20),
    ("1120S", "BalanceSheet", "Loans & Other Investments",   20, "L-8b",  "Other Investments",                           30),
    ("1120S", "BalanceSheet", "Fixed & Intangible Assets",   30, "L-9a",  "Buildings & Other Depreciable Assets",        10),
    ("1120S", "BalanceSheet", "Fixed & Intangible Assets",   30, "L-9b",  "Less: Accumulated Depreciation",              20),
    ("1120S", "BalanceSheet", "Fixed & Intangible Assets",   30, "L-10a", "Depletable Assets",                           30),
    ("1120S", "BalanceSheet", "Fixed & Intangible Assets",   30, "L-10b", "Less: Accumulated Depletion",                 40),
    ("1120S", "BalanceSheet", "Fixed & Intangible Assets",   30, "L-11",  "Land (net of any amortization)",              50),
    ("1120S", "BalanceSheet", "Fixed & Intangible Assets",   30, "L-12a", "Intangible Assets (amortizable only)",        60),
    ("1120S", "BalanceSheet", "Fixed & Intangible Assets",   30, "L-12b", "Less: Accumulated Amortization",              70),
    ("1120S", "BalanceSheet", "Fixed & Intangible Assets",   30, "L-13",  "Other Assets",                                80),

    # ── Schedule L — Liabilities ──────────────────────────────────────────
    ("1120S", "BalanceSheet", "Current Liabilities",         40, "L-15",  "Accounts Payable",                            10),
    ("1120S", "BalanceSheet", "Current Liabilities",         40, "L-16",  "Mortgages, Notes, Bonds Payable < 1 Year",    20),
    ("1120S", "BalanceSheet", "Current Liabilities",         40, "L-17",  "Other Current Liabilities",                   30),
    ("1120S", "BalanceSheet", "Long-Term Liabilities",       50, "L-18",  "Loans from Shareholders",                     10),
    ("1120S", "BalanceSheet", "Long-Term Liabilities",       50, "L-19",  "Mortgages, Notes, Bonds Payable ≥ 1 Year",    20),
    ("1120S", "BalanceSheet", "Long-Term Liabilities",       50, "L-20",  "Other Liabilities",                           30),

    # ── Schedule L — Shareholders' Equity ────────────────────────────────
    ("1120S", "BalanceSheet", "Shareholders' Equity",        60, "L-21",  "Capital Stock",                               10),
    ("1120S", "BalanceSheet", "Shareholders' Equity",        60, "L-22a", "Additional Paid-In Capital",                  20),
    ("1120S", "BalanceSheet", "Shareholders' Equity",        60, "L-22b", "Retained Earnings—Appropriated",              30),
    ("1120S", "BalanceSheet", "Shareholders' Equity",        60, "L-22c", "Retained Earnings—Unappropriated",            40),
    ("1120S", "BalanceSheet", "Shareholders' Equity",        60, "L-22d", "Adjustments to Shareholders' Equity",         50),
    ("1120S", "BalanceSheet", "Shareholders' Equity",        60, "L-22e", "Less: Cost of Treasury Stock",                60),

    # ── Page 1 — Income (Lines 1–6) ───────────────────────────────────────
    ("1120S", "ProfitAndLoss", "Income",                     10, "1a",    "Gross Receipts or Sales",                     10),
    ("1120S", "ProfitAndLoss", "Income",                     10, "1b",    "Returns & Allowances",                        20),
    ("1120S", "ProfitAndLoss", "Income",                     10, "4",     "Net Gain (Loss) — Form 4797",                 30),
    ("1120S", "ProfitAndLoss", "Income",                     10, "5",     "Other Income (Loss)",                         40),

    # ── Page 1 — Cost of Goods Sold (Line 2) ─────────────────────────────
    ("1120S", "ProfitAndLoss", "Cost of Goods Sold",         15, "2",     "Cost of Goods Sold (Form 1125-A)",            10),

    # ── Page 1 — Deductions (Lines 7–19) ─────────────────────────────────
    ("1120S", "ProfitAndLoss", "Deductions",                 20, "7",     "Compensation of Officers",                    10),
    ("1120S", "ProfitAndLoss", "Deductions",                 20, "8",     "Salaries & Wages (less employment credits)",  20),
    ("1120S", "ProfitAndLoss", "Deductions",                 20, "9",     "Repairs & Maintenance",                       30),
    ("1120S", "ProfitAndLoss", "Deductions",                 20, "10",    "Bad Debts",                                   40),
    ("1120S", "ProfitAndLoss", "Deductions",                 20, "11",    "Rents",                                       50),
    ("1120S", "ProfitAndLoss", "Deductions",                 20, "12",    "Taxes & Licenses",                            60),
    ("1120S", "ProfitAndLoss", "Deductions",                 20, "13",    "Interest Expense",                            70),
    ("1120S", "ProfitAndLoss", "Deductions",                 20, "14",    "Depreciation (not on Form 1125-A)",           80),
    ("1120S", "ProfitAndLoss", "Deductions",                 20, "15",    "Depletion (not oil & gas)",                   90),
    ("1120S", "ProfitAndLoss", "Deductions",                 20, "16",    "Advertising",                                100),
    ("1120S", "ProfitAndLoss", "Deductions",                 20, "17",    "Pension, Profit-Sharing, etc., Plans",       110),
    ("1120S", "ProfitAndLoss", "Deductions",                 20, "18",    "Employee Benefit Programs",                  120),
    ("1120S", "ProfitAndLoss", "Deductions",                 20, "19",    "Other Deductions",                           130),

    # ── Schedule K — Pass-Through Items ──────────────────────────────────
    ("1120S", "ProfitAndLoss", "Schedule K — Pass-Through",  30, "K-2",   "Net Rental Real Estate Income (Loss)",        10),
    ("1120S", "ProfitAndLoss", "Schedule K — Pass-Through",  30, "K-3c",  "Other Net Rental Income (Loss)",              20),
    ("1120S", "ProfitAndLoss", "Schedule K — Pass-Through",  30, "K-4",   "Interest Income",                             30),
    ("1120S", "ProfitAndLoss", "Schedule K — Pass-Through",  30, "K-5a",  "Ordinary Dividends",                          40),
    ("1120S", "ProfitAndLoss", "Schedule K — Pass-Through",  30, "K-5b",  "Qualified Dividends",                         50),
    ("1120S", "ProfitAndLoss", "Schedule K — Pass-Through",  30, "K-6",   "Royalties",                                   60),
    ("1120S", "ProfitAndLoss", "Schedule K — Pass-Through",  30, "K-7",   "Net Short-Term Capital Gain (Loss)",          70),
    ("1120S", "ProfitAndLoss", "Schedule K — Pass-Through",  30, "K-8a",  "Net Long-Term Capital Gain (Loss)",           80),
    ("1120S", "ProfitAndLoss", "Schedule K — Pass-Through",  30, "K-8b",  "Collectibles (28%) Gain (Loss)",              90),
    ("1120S", "ProfitAndLoss", "Schedule K — Pass-Through",  30, "K-8c",  "Unrecaptured Sec. 1250 Gain",                100),
    ("1120S", "ProfitAndLoss", "Schedule K — Pass-Through",  30, "K-9",   "Net Section 1231 Gain (Loss)",               110),
    ("1120S", "ProfitAndLoss", "Schedule K — Pass-Through",  30, "K-10",  "Other Income (Loss)",                        120),
    ("1120S", "ProfitAndLoss", "Schedule K — Pass-Through",  30, "K-11",  "Section 179 Deduction",                      130),
    ("1120S", "ProfitAndLoss", "Schedule K — Pass-Through",  30, "K-12a", "Charitable Contributions",                   140),

    # ══════════════════════════════════════════════════════════════════════
    # FORM 1065  (Partnership)
    # ══════════════════════════════════════════════════════════════════════

    # ── Schedule L — Assets ───────────────────────────────────────────────
    ("1065", "BalanceSheet", "Current Assets",               10, "L-1",   "Cash",                                        10),
    ("1065", "BalanceSheet", "Current Assets",               10, "L-2a",  "Trade Notes & Accounts Receivable",           20),
    ("1065", "BalanceSheet", "Current Assets",               10, "L-2b",  "Less: Allowance for Bad Debts",               30),
    ("1065", "BalanceSheet", "Current Assets",               10, "L-3",   "Inventories",                                 40),
    ("1065", "BalanceSheet", "Current Assets",               10, "L-4",   "U.S. Government Obligations",                 50),
    ("1065", "BalanceSheet", "Current Assets",               10, "L-5",   "Tax-Exempt Securities",                       60),
    ("1065", "BalanceSheet", "Current Assets",               10, "L-6",   "Other Current Assets",                        70),
    ("1065", "BalanceSheet", "Loans & Other Investments",    20, "L-7",   "Loans to Partners (or Persons Related)",      10),
    ("1065", "BalanceSheet", "Loans & Other Investments",    20, "L-8a",  "Mortgage & Real Estate Loans",                20),
    ("1065", "BalanceSheet", "Loans & Other Investments",    20, "L-8b",  "Other Investments",                           30),
    ("1065", "BalanceSheet", "Fixed & Intangible Assets",    30, "L-9a",  "Buildings & Other Depreciable Assets",        10),
    ("1065", "BalanceSheet", "Fixed & Intangible Assets",    30, "L-9b",  "Less: Accumulated Depreciation",              20),
    ("1065", "BalanceSheet", "Fixed & Intangible Assets",    30, "L-10a", "Depletable Assets",                           30),
    ("1065", "BalanceSheet", "Fixed & Intangible Assets",    30, "L-10b", "Less: Accumulated Depletion",                 40),
    ("1065", "BalanceSheet", "Fixed & Intangible Assets",    30, "L-11",  "Land (net of any amortization)",              50),
    ("1065", "BalanceSheet", "Fixed & Intangible Assets",    30, "L-12a", "Intangible Assets (amortizable only)",        60),
    ("1065", "BalanceSheet", "Fixed & Intangible Assets",    30, "L-12b", "Less: Accumulated Amortization",              70),
    ("1065", "BalanceSheet", "Fixed & Intangible Assets",    30, "L-13",  "Other Assets",                                80),

    # ── Schedule L — Liabilities & Partners' Capital ─────────────────────
    ("1065", "BalanceSheet", "Current Liabilities",          40, "L-15",  "Accounts Payable",                            10),
    ("1065", "BalanceSheet", "Current Liabilities",          40, "L-16",  "Mortgages, Notes, Bonds Payable < 1 Year",    20),
    ("1065", "BalanceSheet", "Current Liabilities",          40, "L-17",  "Other Current Liabilities",                   30),
    ("1065", "BalanceSheet", "Long-Term Liabilities",        50, "L-18",  "Loans from Partners (or Persons Related)",    10),
    ("1065", "BalanceSheet", "Long-Term Liabilities",        50, "L-19",  "Mortgages, Notes, Bonds Payable ≥ 1 Year",    20),
    ("1065", "BalanceSheet", "Long-Term Liabilities",        50, "L-20",  "Other Liabilities",                           30),
    ("1065", "BalanceSheet", "Partners' Capital",            60, "L-21a", "Capital Contributed — Cash",                  10),
    ("1065", "BalanceSheet", "Partners' Capital",            60, "L-21b", "Capital Contributed — Property",              20),
    ("1065", "BalanceSheet", "Partners' Capital",            60, "L-21c", "Partners' Capital (Beginning of Year)",       30),
    ("1065", "BalanceSheet", "Partners' Capital",            60, "L-21d", "Other Increases / (Decreases)",               40),
    ("1065", "BalanceSheet", "Partners' Capital",            60, "L-21e", "Withdrawals & Distributions",                 50),

    # ── Page 1 — Income (Lines 1–8) ───────────────────────────────────────
    ("1065", "ProfitAndLoss", "Income",                      10, "1a",    "Gross Receipts or Sales",                     10),
    ("1065", "ProfitAndLoss", "Income",                      10, "1b",    "Returns & Allowances",                        20),
    ("1065", "ProfitAndLoss", "Income",                      10, "4",     "Ordinary Income (Loss) — Other Partnerships", 30),
    ("1065", "ProfitAndLoss", "Income",                      10, "5",     "Net Farm Profit (Loss)",                      40),
    ("1065", "ProfitAndLoss", "Income",                      10, "6",     "Net Gain (Loss) — Form 4797",                 50),
    ("1065", "ProfitAndLoss", "Income",                      10, "7",     "Other Income (Loss)",                         60),

    # ── Page 1 — Cost of Goods Sold (Line 2) ─────────────────────────────
    ("1065", "ProfitAndLoss", "Cost of Goods Sold",          15, "2",     "Cost of Goods Sold (Form 1125-A)",            10),

    # ── Page 1 — Deductions (Lines 9–20) ─────────────────────────────────
    ("1065", "ProfitAndLoss", "Deductions",                  20, "9",     "Salaries & Wages (other than to partners)",   10),
    ("1065", "ProfitAndLoss", "Deductions",                  20, "10",    "Guaranteed Payments — Services",              20),
    ("1065", "ProfitAndLoss", "Deductions",                  20, "11",    "Repairs & Maintenance",                       30),
    ("1065", "ProfitAndLoss", "Deductions",                  20, "12",    "Bad Debts",                                   40),
    ("1065", "ProfitAndLoss", "Deductions",                  20, "13",    "Rent",                                        50),
    ("1065", "ProfitAndLoss", "Deductions",                  20, "14",    "Taxes & Licenses",                            60),
    ("1065", "ProfitAndLoss", "Deductions",                  20, "15",    "Interest Expense",                            70),
    ("1065", "ProfitAndLoss", "Deductions",                  20, "16a",   "Depreciation (Form 4562 filed)",              80),
    ("1065", "ProfitAndLoss", "Deductions",                  20, "17",    "Depletion (not oil & gas)",                   90),
    ("1065", "ProfitAndLoss", "Deductions",                  20, "18",    "Retirement Plans, etc.",                     100),
    ("1065", "ProfitAndLoss", "Deductions",                  20, "19",    "Employee Benefit Programs",                  110),
    ("1065", "ProfitAndLoss", "Deductions",                  20, "20",    "Other Deductions",                           120),

    # ── Schedule K — Pass-Through Items ──────────────────────────────────
    ("1065", "ProfitAndLoss", "Schedule K — Pass-Through",   30, "K-2",   "Net Rental Real Estate Income (Loss)",        10),
    ("1065", "ProfitAndLoss", "Schedule K — Pass-Through",   30, "K-3c",  "Other Net Rental Income (Loss)",              20),
    ("1065", "ProfitAndLoss", "Schedule K — Pass-Through",   30, "K-4",   "Guaranteed Payments for Services",            30),
    ("1065", "ProfitAndLoss", "Schedule K — Pass-Through",   30, "K-5",   "Guaranteed Payments for Capital",             40),
    ("1065", "ProfitAndLoss", "Schedule K — Pass-Through",   30, "K-7",   "Interest Income",                             50),
    ("1065", "ProfitAndLoss", "Schedule K — Pass-Through",   30, "K-8a",  "Ordinary Dividends",                          60),
    ("1065", "ProfitAndLoss", "Schedule K — Pass-Through",   30, "K-8b",  "Qualified Dividends",                         70),
    ("1065", "ProfitAndLoss", "Schedule K — Pass-Through",   30, "K-8c",  "Dividend Equivalents",                        80),
    ("1065", "ProfitAndLoss", "Schedule K — Pass-Through",   30, "K-9",   "Royalties",                                   90),
    ("1065", "ProfitAndLoss", "Schedule K — Pass-Through",   30, "K-10",  "Net Short-Term Capital Gain (Loss)",         100),
    ("1065", "ProfitAndLoss", "Schedule K — Pass-Through",   30, "K-11a", "Net Long-Term Capital Gain (Loss)",          110),
    ("1065", "ProfitAndLoss", "Schedule K — Pass-Through",   30, "K-11b", "Collectibles (28%) Gain (Loss)",             120),
    ("1065", "ProfitAndLoss", "Schedule K — Pass-Through",   30, "K-11c", "Unrecaptured Sec. 1250 Gain",                130),
    ("1065", "ProfitAndLoss", "Schedule K — Pass-Through",   30, "K-12",  "Net Section 1231 Gain (Loss)",               140),
    ("1065", "ProfitAndLoss", "Schedule K — Pass-Through",   30, "K-13",  "Other Income (Loss)",                        150),
    ("1065", "ProfitAndLoss", "Schedule K — Pass-Through",   30, "K-14",  "Section 179 Deduction",                      160),
    ("1065", "ProfitAndLoss", "Schedule K — Pass-Through",   30, "K-15a", "Charitable Contributions",                   170),

    # ══════════════════════════════════════════════════════════════════════
    # FORM 1120  (C-Corporation)
    # ══════════════════════════════════════════════════════════════════════

    # ── Schedule L — Assets ───────────────────────────────────────────────
    ("1120", "BalanceSheet", "Current Assets",               10, "L-1",   "Cash",                                        10),
    ("1120", "BalanceSheet", "Current Assets",               10, "L-2a",  "Trade Notes & Accounts Receivable",           20),
    ("1120", "BalanceSheet", "Current Assets",               10, "L-2b",  "Less: Allowance for Bad Debts",               30),
    ("1120", "BalanceSheet", "Current Assets",               10, "L-3",   "Inventories",                                 40),
    ("1120", "BalanceSheet", "Current Assets",               10, "L-4",   "U.S. Government Obligations",                 50),
    ("1120", "BalanceSheet", "Current Assets",               10, "L-5",   "Tax-Exempt Securities",                       60),
    ("1120", "BalanceSheet", "Current Assets",               10, "L-6",   "Other Current Assets",                        70),
    ("1120", "BalanceSheet", "Loans & Other Investments",    20, "L-7",   "Loans to Shareholders",                       10),
    ("1120", "BalanceSheet", "Loans & Other Investments",    20, "L-8a",  "Mortgage & Real Estate Loans",                20),
    ("1120", "BalanceSheet", "Loans & Other Investments",    20, "L-8b",  "Other Investments",                           30),
    ("1120", "BalanceSheet", "Fixed & Intangible Assets",    30, "L-9a",  "Buildings & Other Depreciable Assets",        10),
    ("1120", "BalanceSheet", "Fixed & Intangible Assets",    30, "L-9b",  "Less: Accumulated Depreciation",              20),
    ("1120", "BalanceSheet", "Fixed & Intangible Assets",    30, "L-10a", "Depletable Assets",                           30),
    ("1120", "BalanceSheet", "Fixed & Intangible Assets",    30, "L-10b", "Less: Accumulated Depletion",                 40),
    ("1120", "BalanceSheet", "Fixed & Intangible Assets",    30, "L-11",  "Land (net of any amortization)",              50),
    ("1120", "BalanceSheet", "Fixed & Intangible Assets",    30, "L-12a", "Intangible Assets (amortizable only)",        60),
    ("1120", "BalanceSheet", "Fixed & Intangible Assets",    30, "L-12b", "Less: Accumulated Amortization",              70),
    ("1120", "BalanceSheet", "Fixed & Intangible Assets",    30, "L-13",  "Other Assets",                                80),

    # ── Schedule L — Liabilities & Stockholders' Equity ──────────────────
    ("1120", "BalanceSheet", "Current Liabilities",          40, "L-15",  "Accounts Payable",                            10),
    ("1120", "BalanceSheet", "Current Liabilities",          40, "L-16",  "Mortgages, Notes, Bonds Payable < 1 Year",    20),
    ("1120", "BalanceSheet", "Current Liabilities",          40, "L-17",  "Other Current Liabilities",                   30),
    ("1120", "BalanceSheet", "Long-Term Liabilities",        50, "L-18",  "Loans from Shareholders",                     10),
    ("1120", "BalanceSheet", "Long-Term Liabilities",        50, "L-19",  "Mortgages, Notes, Bonds Payable ≥ 1 Year",    20),
    ("1120", "BalanceSheet", "Long-Term Liabilities",        50, "L-20",  "Other Liabilities",                           30),
    ("1120", "BalanceSheet", "Stockholders' Equity",         60, "L-21",  "Capital Stock — Preferred",                   10),
    ("1120", "BalanceSheet", "Stockholders' Equity",         60, "L-22",  "Capital Stock — Common",                      20),
    ("1120", "BalanceSheet", "Stockholders' Equity",         60, "L-23",  "Additional Paid-In Capital",                  30),
    ("1120", "BalanceSheet", "Stockholders' Equity",         60, "L-24",  "Retained Earnings—Appropriated",              40),
    ("1120", "BalanceSheet", "Stockholders' Equity",         60, "L-25",  "Retained Earnings—Unappropriated",            50),
    ("1120", "BalanceSheet", "Stockholders' Equity",         60, "L-26",  "Adjustments to Shareholders' Equity",         60),
    ("1120", "BalanceSheet", "Stockholders' Equity",         60, "L-27",  "Less: Cost of Treasury Stock",                70),

    # ── Page 1 — Income (Lines 1–11) ─────────────────────────────────────
    ("1120", "ProfitAndLoss", "Income",                      10, "1a",    "Gross Receipts or Sales",                     10),
    ("1120", "ProfitAndLoss", "Income",                      10, "1b",    "Returns & Allowances",                        20),
    ("1120", "ProfitAndLoss", "Income",                      10, "4",     "Dividends & Inclusions",                      30),
    ("1120", "ProfitAndLoss", "Income",                      10, "5",     "Interest",                                    40),
    ("1120", "ProfitAndLoss", "Income",                      10, "6",     "Gross Rents",                                 50),
    ("1120", "ProfitAndLoss", "Income",                      10, "7",     "Gross Royalties",                             60),
    ("1120", "ProfitAndLoss", "Income",                      10, "8",     "Capital Gain Net Income",                     70),
    ("1120", "ProfitAndLoss", "Income",                      10, "9",     "Net Gain (Loss) — Form 4797",                 80),
    ("1120", "ProfitAndLoss", "Income",                      10, "10",    "Other Income",                                90),

    # ── Cost of Goods Sold (Line 2) ───────────────────────────────────────
    ("1120", "ProfitAndLoss", "Cost of Goods Sold",          15, "2",     "Cost of Goods Sold (Form 1125-A)",            10),

    # ── Page 1 — Deductions (Lines 12–29) ────────────────────────────────
    ("1120", "ProfitAndLoss", "Deductions",                  20, "12",    "Compensation of Officers",                    10),
    ("1120", "ProfitAndLoss", "Deductions",                  20, "13",    "Salaries & Wages",                            20),
    ("1120", "ProfitAndLoss", "Deductions",                  20, "14",    "Repairs & Maintenance",                       30),
    ("1120", "ProfitAndLoss", "Deductions",                  20, "15",    "Bad Debts",                                   40),
    ("1120", "ProfitAndLoss", "Deductions",                  20, "16",    "Rents",                                       50),
    ("1120", "ProfitAndLoss", "Deductions",                  20, "17",    "Taxes & Licenses",                            60),
    ("1120", "ProfitAndLoss", "Deductions",                  20, "18",    "Interest",                                    70),
    ("1120", "ProfitAndLoss", "Deductions",                  20, "19",    "Charitable Contributions",                    80),
    ("1120", "ProfitAndLoss", "Deductions",                  20, "20",    "Depreciation",                                90),
    ("1120", "ProfitAndLoss", "Deductions",                  20, "21",    "Depletion",                                  100),
    ("1120", "ProfitAndLoss", "Deductions",                  20, "22",    "Advertising",                                110),
    ("1120", "ProfitAndLoss", "Deductions",                  20, "23",    "Pension, Profit-Sharing, etc., Plans",       120),
    ("1120", "ProfitAndLoss", "Deductions",                  20, "24",    "Employee Benefit Programs",                  130),
    ("1120", "ProfitAndLoss", "Deductions",                  20, "26",    "Other Deductions",                           140),

    # ══════════════════════════════════════════════════════════════════════
    # SCHEDULE C  (Sole Proprietor — no formal Schedule L)
    # ══════════════════════════════════════════════════════════════════════

    ("ScheduleC", "BalanceSheet", "Assets",                  10, "BS-1",  "Cash & Bank Accounts",                        10),
    ("ScheduleC", "BalanceSheet", "Assets",                  10, "BS-2",  "Accounts Receivable",                         20),
    ("ScheduleC", "BalanceSheet", "Assets",                  10, "BS-3",  "Inventory",                                   30),
    ("ScheduleC", "BalanceSheet", "Assets",                  10, "BS-4",  "Fixed Assets — Net",                          40),
    ("ScheduleC", "BalanceSheet", "Assets",                  10, "BS-5",  "Other Assets",                                50),
    ("ScheduleC", "BalanceSheet", "Liabilities",             20, "BS-6",  "Accounts Payable",                            10),
    ("ScheduleC", "BalanceSheet", "Liabilities",             20, "BS-7",  "Notes Payable",                               20),
    ("ScheduleC", "BalanceSheet", "Liabilities",             20, "BS-8",  "Other Liabilities",                           30),
    ("ScheduleC", "BalanceSheet", "Owner's Equity",          30, "BS-9",  "Owner's Capital",                             10),
    ("ScheduleC", "BalanceSheet", "Owner's Equity",          30, "BS-10", "Owner's Draws",                               20),

    # ── Part I — Gross Income ─────────────────────────────────────────────
    ("ScheduleC", "ProfitAndLoss", "Gross Income",           10, "1",     "Gross Receipts or Sales",                     10),
    ("ScheduleC", "ProfitAndLoss", "Gross Income",           10, "2",     "Returns & Allowances",                        20),
    ("ScheduleC", "ProfitAndLoss", "Gross Income",           10, "6",     "Other Income",                                30),

    # ── Cost of Goods Sold (Line 4) ───────────────────────────────────────
    ("ScheduleC", "ProfitAndLoss", "Cost of Goods Sold",     15, "4",     "Cost of Goods Sold",                          10),

    # ── Part II — Expenses ────────────────────────────────────────────────
    ("ScheduleC", "ProfitAndLoss", "Expenses",               20, "8",     "Advertising",                                 10),
    ("ScheduleC", "ProfitAndLoss", "Expenses",               20, "9",     "Car & Truck Expenses",                        20),
    ("ScheduleC", "ProfitAndLoss", "Expenses",               20, "10",    "Commissions & Fees",                          30),
    ("ScheduleC", "ProfitAndLoss", "Expenses",               20, "11",    "Contract Labor",                              40),
    ("ScheduleC", "ProfitAndLoss", "Expenses",               20, "12",    "Depletion",                                   50),
    ("ScheduleC", "ProfitAndLoss", "Expenses",               20, "13",    "Depreciation & Section 179",                  60),
    ("ScheduleC", "ProfitAndLoss", "Expenses",               20, "14",    "Employee Benefit Programs",                   70),
    ("ScheduleC", "ProfitAndLoss", "Expenses",               20, "15",    "Insurance (other than health)",               80),
    ("ScheduleC", "ProfitAndLoss", "Expenses",               20, "16a",   "Mortgage Interest",                           90),
    ("ScheduleC", "ProfitAndLoss", "Expenses",               20, "16b",   "Other Interest",                             100),
    ("ScheduleC", "ProfitAndLoss", "Expenses",               20, "17",    "Legal & Professional Fees",                  110),
    ("ScheduleC", "ProfitAndLoss", "Expenses",               20, "18",    "Office Expense",                             120),
    ("ScheduleC", "ProfitAndLoss", "Expenses",               20, "19",    "Pension & Profit-Sharing Plans",             130),
    ("ScheduleC", "ProfitAndLoss", "Expenses",               20, "20a",   "Rent / Lease — Vehicles, Machinery",         140),
    ("ScheduleC", "ProfitAndLoss", "Expenses",               20, "20b",   "Rent / Lease — Other Business Property",     150),
    ("ScheduleC", "ProfitAndLoss", "Expenses",               20, "21",    "Repairs & Maintenance",                      160),
    ("ScheduleC", "ProfitAndLoss", "Expenses",               20, "22",    "Supplies",                                   170),
    ("ScheduleC", "ProfitAndLoss", "Expenses",               20, "23",    "Taxes & Licenses",                           180),
    ("ScheduleC", "ProfitAndLoss", "Expenses",               20, "24a",   "Travel",                                     190),
    ("ScheduleC", "ProfitAndLoss", "Expenses",               20, "24b",   "Meals (50% deductible)",                     200),
    ("ScheduleC", "ProfitAndLoss", "Expenses",               20, "25",    "Utilities",                                  210),
    ("ScheduleC", "ProfitAndLoss", "Expenses",               20, "26",    "Wages",                                      220),
    ("ScheduleC", "ProfitAndLoss", "Expenses",               20, "27a",   "Other Expenses",                             230),

    # ══════════════════════════════════════════════════════════════════════
    # FORM 990  (Non-Profit Organization)
    # Balance Sheet = Part X
    # Revenue = Part VIII / Expenses = Part IX
    # ══════════════════════════════════════════════════════════════════════

    # ── Part X — Assets ───────────────────────────────────────────────────
    ("990", "BalanceSheet", "Assets",                        10, "X-1",   "Cash — Non-Interest Bearing",                 10),
    ("990", "BalanceSheet", "Assets",                        10, "X-2",   "Savings & Temporary Cash Investments",        20),
    ("990", "BalanceSheet", "Assets",                        10, "X-3",   "Pledges & Grants Receivable, Net",            30),
    ("990", "BalanceSheet", "Assets",                        10, "X-4",   "Accounts Receivable, Net",                    40),
    ("990", "BalanceSheet", "Assets",                        10, "X-5",   "Receivables — Officers, Directors, etc.",     50),
    ("990", "BalanceSheet", "Assets",                        10, "X-6",   "Receivables — Disqualified Persons",          60),
    ("990", "BalanceSheet", "Assets",                        10, "X-7",   "Notes & Loans Receivable, Net",               70),
    ("990", "BalanceSheet", "Assets",                        10, "X-8",   "Inventories for Sale or Use",                 80),
    ("990", "BalanceSheet", "Assets",                        10, "X-9",   "Prepaid Expenses & Deferred Charges",         90),
    ("990", "BalanceSheet", "Assets",                        10, "X-10a", "Land, Buildings & Equipment — Gross",        100),
    ("990", "BalanceSheet", "Assets",                        10, "X-10b", "Less: Accumulated Depreciation",             110),
    ("990", "BalanceSheet", "Assets",                        10, "X-11",  "Investments — Publicly Traded Securities",   120),
    ("990", "BalanceSheet", "Assets",                        10, "X-12",  "Investments — Other Securities",             130),
    ("990", "BalanceSheet", "Assets",                        10, "X-13",  "Investments — Program-Related",              140),
    ("990", "BalanceSheet", "Assets",                        10, "X-14",  "Intangible Assets",                          150),
    ("990", "BalanceSheet", "Assets",                        10, "X-15",  "Other Assets",                               160),

    # ── Part X — Liabilities ──────────────────────────────────────────────
    ("990", "BalanceSheet", "Liabilities",                   20, "X-17",  "Accounts Payable & Accrued Expenses",         10),
    ("990", "BalanceSheet", "Liabilities",                   20, "X-18",  "Grants Payable",                              20),
    ("990", "BalanceSheet", "Liabilities",                   20, "X-19",  "Deferred Revenue",                            30),
    ("990", "BalanceSheet", "Liabilities",                   20, "X-20",  "Tax-Exempt Bond Liabilities",                 40),
    ("990", "BalanceSheet", "Liabilities",                   20, "X-21",  "Escrow or Custodial Account Liability",       50),
    ("990", "BalanceSheet", "Liabilities",                   20, "X-22",  "Loans Payable — Officers, Directors, etc.",   60),
    ("990", "BalanceSheet", "Liabilities",                   20, "X-23",  "Secured Mortgages & Notes Payable",           70),
    ("990", "BalanceSheet", "Liabilities",                   20, "X-24",  "Unsecured Notes & Loans Payable",             80),
    ("990", "BalanceSheet", "Liabilities",                   20, "X-25",  "Other Liabilities",                           90),

    # ── Part X — Net Assets ───────────────────────────────────────────────
    ("990", "BalanceSheet", "Net Assets",                    30, "X-27",  "Net Assets Without Donor Restrictions",       10),
    ("990", "BalanceSheet", "Net Assets",                    30, "X-28",  "Net Assets With Donor Restrictions",          20),

    # ── Part VIII — Revenue ───────────────────────────────────────────────
    ("990", "ProfitAndLoss", "Revenue (Part VIII)",          10, "VIII-1h","Total Contributions, Gifts & Grants",        10),
    ("990", "ProfitAndLoss", "Revenue (Part VIII)",          10, "VIII-2g","Total Program Service Revenue",              20),
    ("990", "ProfitAndLoss", "Revenue (Part VIII)",          10, "VIII-3", "Investment Income",                          30),
    ("990", "ProfitAndLoss", "Revenue (Part VIII)",          10, "VIII-6d","Net Royalties",                              40),
    ("990", "ProfitAndLoss", "Revenue (Part VIII)",          10, "VIII-7d","Net Rental Income (Loss)",                   50),
    ("990", "ProfitAndLoss", "Revenue (Part VIII)",          10, "VIII-8c","Net Gain (Loss) from Asset Sales",           60),
    ("990", "ProfitAndLoss", "Revenue (Part VIII)",          10, "VIII-9c","Net Fundraising Event Income (Loss)",        70),
    ("990", "ProfitAndLoss", "Revenue (Part VIII)",          10, "VIII-10c","Net Gaming Activities Income",              80),
    ("990", "ProfitAndLoss", "Revenue (Part VIII)",          10, "VIII-11d","Net Sales of Inventory",                    90),
    ("990", "ProfitAndLoss", "Revenue (Part VIII)",          10, "VIII-12","Other Revenue",                             100),

    # ── Part IX — Functional Expenses ────────────────────────────────────
    ("990", "ProfitAndLoss", "Functional Expenses (Part IX)",20, "IX-1",  "Grants to Domestic Organizations",            10),
    ("990", "ProfitAndLoss", "Functional Expenses (Part IX)",20, "IX-2",  "Grants to Domestic Individuals",              20),
    ("990", "ProfitAndLoss", "Functional Expenses (Part IX)",20, "IX-3",  "Grants to Foreign Organizations",             30),
    ("990", "ProfitAndLoss", "Functional Expenses (Part IX)",20, "IX-4",  "Benefits Paid to Members",                    40),
    ("990", "ProfitAndLoss", "Functional Expenses (Part IX)",20, "IX-5",  "Compensation — Officers, Directors, Trustees",50),
    ("990", "ProfitAndLoss", "Functional Expenses (Part IX)",20, "IX-7",  "Other Salaries & Wages",                      60),
    ("990", "ProfitAndLoss", "Functional Expenses (Part IX)",20, "IX-8",  "Pension Plan Accruals & Contributions",       70),
    ("990", "ProfitAndLoss", "Functional Expenses (Part IX)",20, "IX-9",  "Other Employee Benefits",                     80),
    ("990", "ProfitAndLoss", "Functional Expenses (Part IX)",20, "IX-10", "Payroll Taxes",                               90),
    ("990", "ProfitAndLoss", "Functional Expenses (Part IX)",20, "IX-11a","Management Fees",                            100),
    ("990", "ProfitAndLoss", "Functional Expenses (Part IX)",20, "IX-11b","Legal Fees",                                 110),
    ("990", "ProfitAndLoss", "Functional Expenses (Part IX)",20, "IX-11c","Accounting Fees",                            120),
    ("990", "ProfitAndLoss", "Functional Expenses (Part IX)",20, "IX-11e","Professional Fundraising Fees",              130),
    ("990", "ProfitAndLoss", "Functional Expenses (Part IX)",20, "IX-11f","Investment Management Fees",                 140),
    ("990", "ProfitAndLoss", "Functional Expenses (Part IX)",20, "IX-11g","Other Professional Fees",                    150),
    ("990", "ProfitAndLoss", "Functional Expenses (Part IX)",20, "IX-12", "Advertising & Promotion",                    160),
    ("990", "ProfitAndLoss", "Functional Expenses (Part IX)",20, "IX-13", "Office Expenses",                            170),
    ("990", "ProfitAndLoss", "Functional Expenses (Part IX)",20, "IX-14", "Information Technology",                     180),
    ("990", "ProfitAndLoss", "Functional Expenses (Part IX)",20, "IX-16a","Occupancy",                                  190),
    ("990", "ProfitAndLoss", "Functional Expenses (Part IX)",20, "IX-17", "Travel",                                     200),
    ("990", "ProfitAndLoss", "Functional Expenses (Part IX)",20, "IX-20", "Interest",                                   210),
    ("990", "ProfitAndLoss", "Functional Expenses (Part IX)",20, "IX-22", "Depreciation, Depletion & Amortization",     220),
    ("990", "ProfitAndLoss", "Functional Expenses (Part IX)",20, "IX-23", "Insurance",                                  230),
    ("990", "ProfitAndLoss", "Functional Expenses (Part IX)",20, "IX-24a","Other Expenses",                             240),

    # ══════════════════════════════════════════════════════════════════════
    # FORM 1041  (Estate & Trust)
    # No formal Schedule L — informal BS provided
    # ══════════════════════════════════════════════════════════════════════

    # ── Informal Balance Sheet ────────────────────────────────────────────
    ("1041", "BalanceSheet", "Assets",                       10, "BS-1",  "Cash & Cash Equivalents",                     10),
    ("1041", "BalanceSheet", "Assets",                       10, "BS-2",  "Accounts & Notes Receivable",                 20),
    ("1041", "BalanceSheet", "Assets",                       10, "BS-3",  "Investments — Securities",                    30),
    ("1041", "BalanceSheet", "Assets",                       10, "BS-4",  "Investments — Real Estate",                   40),
    ("1041", "BalanceSheet", "Assets",                       10, "BS-5",  "Other Investments",                           50),
    ("1041", "BalanceSheet", "Assets",                       10, "BS-6",  "Personal Property",                           60),
    ("1041", "BalanceSheet", "Assets",                       10, "BS-7",  "Real Property",                               70),
    ("1041", "BalanceSheet", "Assets",                       10, "BS-8",  "Other Assets",                                80),
    ("1041", "BalanceSheet", "Liabilities",                  20, "BS-9",  "Accounts Payable",                            10),
    ("1041", "BalanceSheet", "Liabilities",                  20, "BS-10", "Taxes Payable",                               20),
    ("1041", "BalanceSheet", "Liabilities",                  20, "BS-11", "Debts of Decedent / Trust Obligations",       30),
    ("1041", "BalanceSheet", "Liabilities",                  20, "BS-12", "Other Liabilities",                           40),
    ("1041", "BalanceSheet", "Trust / Estate Capital",       30, "BS-13", "Estate / Trust Corpus (at inception)",        10),
    ("1041", "BalanceSheet", "Trust / Estate Capital",       30, "BS-14", "Accumulated Net Income",                      20),
    ("1041", "BalanceSheet", "Trust / Estate Capital",       30, "BS-15", "Net Assets / Trust Corpus (Current)",         30),

    # ── Page 1 — Income (Lines 1–9) ───────────────────────────────────────
    ("1041", "ProfitAndLoss", "Income",                      10, "1",     "Interest Income",                             10),
    ("1041", "ProfitAndLoss", "Income",                      10, "2a",    "Ordinary Dividends",                          20),
    ("1041", "ProfitAndLoss", "Income",                      10, "2b",    "Qualified Dividends",                         30),
    ("1041", "ProfitAndLoss", "Income",                      10, "3",     "Business Income or (Loss)",                   40),
    ("1041", "ProfitAndLoss", "Income",                      10, "4",     "Capital Gain or (Loss)",                      50),
    ("1041", "ProfitAndLoss", "Income",                      10, "5",     "Rents, Royalties, Partnerships, Trusts",      60),
    ("1041", "ProfitAndLoss", "Income",                      10, "6",     "Farm Income or (Loss)",                       70),
    ("1041", "ProfitAndLoss", "Income",                      10, "7",     "Ordinary Gain or (Loss)",                     80),
    ("1041", "ProfitAndLoss", "Income",                      10, "8",     "Other Income",                                90),

    # ── Page 1 — Deductions (Lines 10–22) ────────────────────────────────
    ("1041", "ProfitAndLoss", "Deductions",                  20, "10",    "Interest",                                    10),
    ("1041", "ProfitAndLoss", "Deductions",                  20, "11",    "Taxes",                                       20),
    ("1041", "ProfitAndLoss", "Deductions",                  20, "12",    "Fiduciary Fees",                              30),
    ("1041", "ProfitAndLoss", "Deductions",                  20, "13",    "Charitable Deduction",                        40),
    ("1041", "ProfitAndLoss", "Deductions",                  20, "14",    "Attorney, Accountant & Return Preparer Fees", 50),
    ("1041", "ProfitAndLoss", "Deductions",                  20, "15a",   "Other Deductions — Not Subject to 2% Floor",  60),
    ("1041", "ProfitAndLoss", "Deductions",                  20, "15b",   "Other Deductions — Subject to 2% Floor",      70),
    ("1041", "ProfitAndLoss", "Deductions",                  20, "18",    "Income Distribution Deduction",               80),
    ("1041", "ProfitAndLoss", "Deductions",                  20, "22",    "Distributions to Beneficiaries",              90),

    # ══════════════════════════════════════════════════════════════════════
    # TRUST / COURT ACCOUNTING  (custom — no IRS form)
    # Follows standard fiduciary accounting format separating
    # Principal Account and Income Account.
    # ══════════════════════════════════════════════════════════════════════

    # ── Principal Account — Assets ────────────────────────────────────────
    ("TrustAccounting", "BalanceSheet", "Principal Assets",  10, "PA-1",  "Cash — Principal",                            10),
    ("TrustAccounting", "BalanceSheet", "Principal Assets",  10, "PA-2",  "Investment Securities — Principal",           20),
    ("TrustAccounting", "BalanceSheet", "Principal Assets",  10, "PA-3",  "Real Property — Principal",                   30),
    ("TrustAccounting", "BalanceSheet", "Principal Assets",  10, "PA-4",  "Notes Receivable — Principal",                40),
    ("TrustAccounting", "BalanceSheet", "Principal Assets",  10, "PA-5",  "Other Principal Assets",                      50),

    # ── Income Account — Assets ───────────────────────────────────────────
    ("TrustAccounting", "BalanceSheet", "Income Assets",     20, "IA-1",  "Cash — Income",                               10),
    ("TrustAccounting", "BalanceSheet", "Income Assets",     20, "IA-2",  "Accrued Income Receivable",                   20),

    # ── Liabilities ───────────────────────────────────────────────────────
    ("TrustAccounting", "BalanceSheet", "Liabilities",       30, "L-1",   "Accounts Payable",                            10),
    ("TrustAccounting", "BalanceSheet", "Liabilities",       30, "L-2",   "Accrued Expenses",                            20),
    ("TrustAccounting", "BalanceSheet", "Liabilities",       30, "L-3",   "Other Liabilities",                           30),

    # ── Trust Corpus / Net Assets ─────────────────────────────────────────
    ("TrustAccounting", "BalanceSheet", "Trust Corpus & Net Assets", 40, "TC-1", "Trust Corpus (Beginning of Period)",   10),
    ("TrustAccounting", "BalanceSheet", "Trust Corpus & Net Assets", 40, "TC-2", "Net Realized Gains (Losses)",           20),
    ("TrustAccounting", "BalanceSheet", "Trust Corpus & Net Assets", 40, "TC-3", "Other Principal Additions",            30),
    ("TrustAccounting", "BalanceSheet", "Trust Corpus & Net Assets", 40, "TC-4", "Principal Disbursements",              40),
    ("TrustAccounting", "BalanceSheet", "Trust Corpus & Net Assets", 40, "TC-5", "Distributions from Principal",         50),
    ("TrustAccounting", "BalanceSheet", "Trust Corpus & Net Assets", 40, "TC-6", "Accumulated Net Income",               60),

    # ── Income Receipts ───────────────────────────────────────────────────
    ("TrustAccounting", "ProfitAndLoss", "Income Receipts",  10, "IR-1",  "Dividends",                                   10),
    ("TrustAccounting", "ProfitAndLoss", "Income Receipts",  10, "IR-2",  "Interest",                                    20),
    ("TrustAccounting", "ProfitAndLoss", "Income Receipts",  10, "IR-3",  "Rents",                                       30),
    ("TrustAccounting", "ProfitAndLoss", "Income Receipts",  10, "IR-4",  "Royalties",                                   40),
    ("TrustAccounting", "ProfitAndLoss", "Income Receipts",  10, "IR-5",  "Business Income Allocated to Income",         50),
    ("TrustAccounting", "ProfitAndLoss", "Income Receipts",  10, "IR-6",  "Other Income Receipts",                       60),

    # ── Income Disbursements ──────────────────────────────────────────────
    ("TrustAccounting", "ProfitAndLoss", "Income Disbursements", 20, "ID-1", "Fiduciary / Trustee Fees",                 10),
    ("TrustAccounting", "ProfitAndLoss", "Income Disbursements", 20, "ID-2", "Investment Advisory Fees",                 20),
    ("TrustAccounting", "ProfitAndLoss", "Income Disbursements", 20, "ID-3", "Legal & Accounting Fees",                  30),
    ("TrustAccounting", "ProfitAndLoss", "Income Disbursements", 20, "ID-4", "Real Estate Expenses",                     40),
    ("TrustAccounting", "ProfitAndLoss", "Income Disbursements", 20, "ID-5", "Income Taxes Paid",                        50),
    ("TrustAccounting", "ProfitAndLoss", "Income Disbursements", 20, "ID-6", "Other Income Disbursements",               60),

    # ── Distributions ─────────────────────────────────────────────────────
    ("TrustAccounting", "ProfitAndLoss", "Distributions",   30, "D-1",   "Mandatory Distributions to Beneficiaries",    10),
    ("TrustAccounting", "ProfitAndLoss", "Distributions",   30, "D-2",   "Discretionary Distributions to Beneficiaries",20),
    ("TrustAccounting", "ProfitAndLoss", "Distributions",   30, "D-3",   "Distributions from Principal",                30),
]

# Friendly display names for the entity type picker
TEMPLATE_DISPLAY_NAMES: dict[str, str] = {
    "1120S":          "Form 1120-S (S-Corporation)",
    "1065":           "Form 1065 (Partnership)",
    "1120":           "Form 1120 (C-Corporation)",
    "ScheduleC":      "Schedule C (Sole Proprietor)",
    "990":            "Form 990 (Non-Profit)",
    "1041":           "Form 1041 (Estate & Trust)",
    "TrustAccounting":"Trust / Court Accounting",
}
