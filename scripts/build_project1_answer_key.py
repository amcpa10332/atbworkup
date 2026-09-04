"""
Builds the instructor answer-key workup for BUSI 500 Project 1
(Cedar & Slate Creative, LLC -- Schedule C) directly through ATBWorkup's
model layer, using the exact unadjusted trial balance, AJEs, RJEs, and tax
entries specified in:
  "BUSI 500 -- Basic Return Project -- Instructor Control (Draft 4).xlsx"

This does NOT drive the GUI -- it calls the same functions the GUI calls
(create_workup, create_account, create_entry, save_lines, map_accounts,
export_review_package), producing a real .atbw file and .atbr.xlsx package
identical to what a human preparer would get by hand-entering everything.

Run from the project root:
    python scripts/build_project1_answer_key.py
"""
from __future__ import annotations

import datetime
from pathlib import Path

from atbworkup.db.connection import db_connection
from atbworkup.db.settings import set_settings_path, ensure_settings_db, save_profile
from atbworkup.models.job import create_workup, get_job
from atbworkup.models.accounts import create_account, get_account_balances
from atbworkup.models.mappings import get_tax_line_templates, upsert_tax_line, map_accounts
from atbworkup.models.journal_entries import create_entry, save_lines, get_entries
from atbworkup.exporter.review_package import export_review_package

OUT_DIR = Path("Instructor Answer Keys/BUSI 500 Project 1")
OUT_DIR.mkdir(parents=True, exist_ok=True)
ATBW_PATH = OUT_DIR / "2025 Cedar & Slate Creative Instructor Answer Key.atbw"
SETTINGS_PATH = OUT_DIR / "_settings.db"
PREPARER = "Instructor Answer Key"

# ---------------------------------------------------------------------------
# Unadjusted trial balance -- (number, name, type, normal_balance, pbc_balance)
# pbc_balance sign convention: DR = positive, CR = negative.
# ---------------------------------------------------------------------------
ACCOUNTS = [
    ("1000", "Cash",                             "Asset",     "Debit",   85400.0),
    ("1010", "Undeposited Funds",                "Asset",     "Debit",    6000.0),
    ("1100", "Accounts Receivable",               "Asset",     "Debit",   22000.0),
    ("1200", "Prepaid Insurance",                 "Asset",     "Debit",    3600.0),
    ("1500", "Computer & Production Equipment",   "Asset",     "Debit",   32000.0),
    ("1510", "Furniture & Fixtures",               "Asset",     "Debit",   18000.0),
    ("1520", "Leasehold Improvements",             "Asset",     "Debit",       0.0),
    ("1590", "Accumulated Depreciation",           "Asset",     "Credit", -26000.0),
    ("2000", "Accounts Payable",                   "Liability", "Credit", -13500.0),
    ("2200", "Notes Payable",                      "Liability", "Credit", -60000.0),
    ("3000", "Owner's Capital",                    "Equity",    "Credit", -48300.0),
    ("3010", "Opening Balance Equity",             "Equity",    "Credit", -12500.0),
    ("3020", "Owner's Draws",                      "Equity",    "Debit",   70000.0),
    ("4000", "Service Revenue",                    "Revenue",   "Credit", -350000.0),
    ("4100", "Other Business Income",              "Revenue",   "Credit",  -4000.0),
    ("5000", "Contract Labor",                     "Expense",   "Debit",   60000.0),
    ("5100", "Rent Expense",                       "Expense",   "Debit",   42000.0),
    ("5200", "Repairs & Maintenance",              "Expense",   "Debit",   30100.0),
    ("5210", "Software & Subscriptions",           "Expense",   "Debit",   21900.0),
    ("5220", "Office Supplies",                    "Expense",   "Debit",   16700.0),
    ("5230", "Advertising",                        "Expense",   "Debit",    9500.0),
    ("5240", "Legal & Professional Fees",          "Expense",   "Debit",    2400.0),
    ("5250", "Insurance",                          "Expense",   "Debit",   12000.0),
    ("5260", "Utilities",                          "Expense",   "Debit",    8800.0),
    ("5270", "Telephone & Internet",               "Expense",   "Debit",    7200.0),
    ("5280", "Travel",                             "Expense",   "Debit",   12200.0),
    ("5290", "Business Meals",                     "Expense",   "Debit",    4800.0),
    ("5295", "Entertainment",                      "Expense",   "Debit",    3600.0),
    ("5300", "Fines & Penalties",                  "Expense",   "Debit",    1200.0),
    ("5310", "Bad Debt Expense",                   "Expense",   "Debit",    3000.0),
    ("5320", "Taxes & Licenses",                   "Expense",   "Debit",    5500.0),
    ("5330", "Loan Payment Expense",               "Expense",   "Debit",   12000.0),
    ("5340", "Interest Expense",                   "Expense",   "Debit",    2000.0),
    ("5350", "Bank Charges",                       "Expense",   "Debit",    1500.0),
    ("5360", "Federal Estimated Tax Payments",     "Expense",   "Debit",    9000.0),
    ("5370", "Owner Personal Expenses",            "Expense",   "Debit",    2400.0),
    ("5380", "Depreciation Expense",               "Expense",   "Debit",       0.0),
    ("5390", "Dues & Continuing Education",        "Expense",   "Debit",    2000.0),
    ("5400", "Miscellaneous Expense",              "Expense",   "Debit",    7500.0),
]

# account_number -> Schedule C tax line_code (from atbworkup/data/tax_line_seeds.py),
# following the instructor's own "Preliminary Mapping" column in the Unadjusted TB tab.
ACCOUNT_LINE_CODE = {
    "1000": "BS-1", "1010": "BS-1", "1100": "BS-2", "1200": "BS-5",
    "1500": "BS-4", "1510": "BS-4", "1520": "BS-4", "1590": "BS-4",
    "2000": "BS-6", "2200": "BS-7",
    "3000": "BS-9", "3010": "BS-9", "3020": "BS-10",
    "4000": "1", "4100": "6",
    "5000": "11", "5100": "20b", "5200": "21", "5210": "27a", "5220": "18",
    "5230": "8", "5240": "17", "5250": "15", "5260": "25", "5270": "27a",
    "5280": "24a", "5290": "24b", "5295": "27a", "5300": "27a", "5310": "27a",
    "5320": "23", "5330": "27a", "5340": "16b", "5350": "27a", "5360": "27a",
    "5370": "27a", "5380": "13", "5390": "27a", "5400": "27a",
}

ENTRY_DATE = "2025-12-31"

# Each: (entry_type, instructor_id, title, source_ref, [(account_number, amount, memo), ...])
# amount sign: DR = positive, CR = negative. Must sum to 0 per entry.
ENTRIES = [
    ("AJE", "AJE-01", "Loan proceeds recorded as revenue", "L-1", [
        ("4000", 40000.0, "Remove bank borrowing from operating revenue."),
        ("2200", -40000.0, "Record the new borrowing as a liability."),
    ]),
    ("AJE", "AJE-02", "Loan-payment principal and interest", "L-1", [
        ("2200", 8400.0, "Record the principal component of 2025 payments."),
        ("5340", 3600.0, "Record the interest component of 2025 payments."),
        ("5330", -12000.0, "Reverse payments posted entirely to expense."),
    ]),
    ("AJE", "AJE-03", "Repairs versus capital additions", "FA-1", [
        ("1500", 11000.0, "Capitalize the computer and camera purchases."),
        ("1510", 7500.0, "Capitalize the conference-room furniture."),
        ("1520", 9000.0, "Capitalize the permanent electrical and lighting buildout."),
        ("5200", -27500.0, "Remove the capital additions from repairs expense."),
    ]),
    ("AJE", "AJE-04", "Current-year depreciation", "FA-1", [
        ("5380", 9050.0, "Record current-year depreciation from the supplied schedule."),
        ("1590", -9050.0, "Record current-year accumulated depreciation."),
    ]),
    ("AJE", "AJE-05", "Stale Undeposited Funds and duplicate revenue", "UF-1", [
        ("4000", 6000.0, "Reverse the duplicate 2025 revenue."),
        ("1010", -6000.0, "Clear the stale opening balance."),
    ]),
    ("AJE", "AJE-06", "Opening Balance Equity cleanup", "EQ-1", [
        ("3010", 12500.0, "Clear the bookkeeping-conversion balance."),
        ("3000", -12500.0, "Record the confirmed prior-period owner capital."),
    ]),
    ("AJE", "AJE-07", "Federal estimated payments", "OWN-1", [
        ("3020", 9000.0, "Reclassify federal estimates as owner activity."),
        ("5360", -9000.0, "Remove federal estimates from business expense."),
    ]),
    ("AJE", "AJE-08", "Personal charges", "OWN-1", [
        ("3020", 2400.0, "Reclassify clearly personal charges as owner activity."),
        ("5370", -2400.0, "Remove personal charges from business expense."),
    ]),
    ("RJE", "RJE-01", "Miscellaneous expense natural-account reclasses", "MISC-1", [
        ("5220", 1800.0, "Reclassify office purchases from Miscellaneous Expense."),
        ("5210", 2100.0, "Reclassify software charges from Miscellaneous Expense."),
        ("5240", 3600.0, "Reclassify the legal consultation from Miscellaneous Expense."),
        ("5400", -7500.0, "Clear the identified items to their natural classifications."),
    ]),
    ("RJE", "RJE-02", "Bookkeeping and legal services", "CL-1", [
        ("5240", 10000.0, "Reclassify bookkeeping and legal services."),
        ("5000", -10000.0, "Remove nonproduction services from Contract Labor."),
    ]),
    ("RJE", "RJE-03", "Conference registration", "TRV-1", [
        ("5390", 1200.0, "Reclassify the conference registration from Travel."),
        ("5280", -1200.0, "Remove the registration fee from travel costs."),
    ]),
    ("FTJE", "TJE-01", "Accrual-to-cash revenue conversion", "AR-1", [
        ("4000", -45000.0, "Convert accrual revenue to cash receipts using the AR rollforward."),
        ("1100", 45000.0, "Offset the cash-method revenue conversion."),
    ]),
    ("FTJE", "TJE-02", "Cash-method bad-debt treatment", "AR-1", [
        ("1100", 3000.0, "Restore the written-off receivable for the tax-basis rollforward."),
        ("5310", -3000.0, "Remove bad-debt expense for a cash-method taxpayer."),
    ]),
    ("FTJE", "TJE-03", "Accrual-to-cash expense conversion", "AP-1", [
        ("2000", 4500.0, "Convert accrual-basis expenses to cash paid."),
        ("5000", -2000.0, "Reduce expense for the net increase in unpaid contractor bills."),
        ("5240", -1000.0, "Reduce expense for the net increase in unpaid professional bills."),
        ("5230", -1500.0, "Reduce expense for the net increase in unpaid advertising bills."),
    ]),
    ("FTJE", "TJE-04", "Meals limitation", "TAX-1", [
        ("3000", 2400.0, "Offset the nondeductible portion of business meals."),
        ("5290", -2400.0, "Remove the 50% nondeductible portion of meals."),
    ]),
    ("FTJE", "TJE-05", "Nondeductible entertainment", "TAX-1", [
        ("3000", 3600.0, "Offset nondeductible entertainment."),
        ("5295", -3600.0, "Remove nondeductible entertainment expense."),
    ]),
    ("FTJE", "TJE-06", "Nondeductible fines and penalties", "TAX-1", [
        ("3000", 1200.0, "Offset nondeductible fines and penalties."),
        ("5300", -1200.0, "Remove nondeductible fines and penalties."),
    ]),
]


def main():
    if ATBW_PATH.exists():
        ATBW_PATH.unlink()
    if SETTINGS_PATH.exists():
        SETTINGS_PATH.unlink()

    set_settings_path(SETTINGS_PATH)
    ensure_settings_db()
    save_profile(PREPARER, "IAK", None)

    meta = {
        "client_name": "Cedar & Slate Creative, LLC",
        "entity_name": "Cedar & Slate Creative, LLC",
        "tax_year": 2025,
        "entity_type": "ScheduleC",
        "prepared_by": PREPARER,
        "reviewer": None,
        "workpaper_folder": str(OUT_DIR),
        "accounting_system": "Client-supplied accrual-basis books",
    }
    job_id = create_workup(ATBW_PATH, meta)
    print(f"Created workup: {job_id}")

    with db_connection(ATBW_PATH) as conn:
        # ---- Accounts ----
        account_id_by_number = {}
        for number, name, atype, normal, pbc in ACCOUNTS:
            aid = create_account(conn, job_id, number, name, atype, normal, pbc)
            account_id_by_number[number] = aid
        print(f"Created {len(ACCOUNTS)} accounts.")

        total_dr = sum(b for *_, b in ACCOUNTS if b > 0)
        total_cr = sum(-b for *_, b in ACCOUNTS if b < 0)
        print(f"Unadjusted TB: debits {total_dr:,.2f} / credits {total_cr:,.2f}")
        assert abs(total_dr - total_cr) < 0.005, "Unadjusted TB does not balance!"
        assert abs(total_dr - 514300.0) < 0.005, f"Unadjusted TB total {total_dr} != 514,300"

        # ---- Tax line mapping ----
        with db_connection(SETTINGS_PATH) as sconn:
            templates = get_tax_line_templates(sconn, "ScheduleC")
        templates_by_code = {t["line_code"]: t for t in templates}

        tax_line_id_by_code = {}
        for code in set(ACCOUNT_LINE_CODE.values()):
            t = templates_by_code[code]
            tax_line_id_by_code[code] = upsert_tax_line(
                conn,
                entity_type="ScheduleC",
                financial_statement=t["financial_statement"],
                line_code=t["line_code"],
                line_name=t["line_name"],
                sort_order=t["sort_order"],
                section=t["section"],
                section_sort_order=t["section_sort_order"],
                category=t["category"],
            )

        for number, code in ACCOUNT_LINE_CODE.items():
            map_accounts(
                conn, job_id=job_id,
                account_ids=[account_id_by_number[number]],
                tax_line_id=tax_line_id_by_code[code],
                mapped_by=PREPARER,
            )
        print("Mapped all accounts to Schedule C tax lines.")

        # ---- Journal entries ----
        for entry_type, inst_id, title, source_ref, lines in ENTRIES:
            balance = round(sum(amt for _, amt, _ in lines), 2)
            assert balance == 0.0, f"{inst_id} does not balance: {balance}"

            entry = create_entry(
                conn, job_id=job_id, entry_type=entry_type,
                description=f"{inst_id} — {title} (Source: {source_ref})",
                originated_by=PREPARER,
            )
            save_lines(conn, entry["aje_id"], [
                {"account_id": account_id_by_number[num], "amount": amt, "memo": memo}
                for num, amt, memo in lines
            ])
        print(f"Created {len(ENTRIES)} journal entries "
              f"({sum(1 for e in ENTRIES if e[0]=='AJE')} AJE, "
              f"{sum(1 for e in ENTRIES if e[0]=='RJE')} RJE, "
              f"{sum(1 for e in ENTRIES if e[0]=='FTJE')} FTJE).")

        # ---- Validate against the Instructor Control control-summary numbers ----
        # NOTE: the instructor workbook's AJE/RJE/Tax-entry "total" metrics are the
        # sum of gross debit LINES within that entry type (their AJE sheet literally
        # sums the Debit column across every line), not the net-per-account effect.
        # Those differ whenever one account is touched by two entries in opposite
        # directions within the same layer (e.g. Notes Payable: credited $40,000 by
        # AJE-01, debited $8,400 by AJE-02) -- net-per-account hides the gross debit.
        def gross_debit_total(entry_type: str) -> float:
            rows = conn.execute(
                """SELECT COALESCE(SUM(jel.amount), 0)
                   FROM journal_entry_lines jel
                   JOIN journal_entries je ON je.aje_id = jel.aje_id
                   WHERE je.job_id = ? AND je.entry_type = ? AND jel.amount > 0""",
                (job_id, entry_type),
            ).fetchone()
            return round(rows[0], 2)

        balances = get_account_balances(conn, job_id)
        aje_dr = gross_debit_total("AJE")
        rje_dr = gross_debit_total("RJE")
        ftje_dr = gross_debit_total("FTJE")
        adj_book_ni = -sum(
            b["final"] for b in balances
            if b["financial_statement"] == "ProfitAndLoss"
        )
        tax_ni = -sum(
            b["ftax"] for b in balances
            if b["financial_statement"] == "ProfitAndLoss"
        )
        note_payable_end = -next(b["final"] for b in balances if b["account_number"] == "2200")
        fixed_asset_cost_end = sum(
            b["final"] for b in balances if b["account_number"] in ("1500", "1510", "1520")
        )
        accum_dep_end = -next(b["final"] for b in balances if b["account_number"] == "1590")

        checks = [
            ("AJE total", aje_dr, 118450.0),
            ("RJE total", rje_dr, 18700.0),
            ("Tax-entry total", ftje_dr, 59700.0),
            ("Adjusted book net income", adj_book_ni, 68950.0),
            ("Schedule C net profit (tax basis)", tax_ni, 128650.0),
            ("Ending note payable", note_payable_end, 91600.0),
            ("Adjusted fixed-asset cost", fixed_asset_cost_end, 77500.0),
            ("Ending accumulated depreciation", accum_dep_end, 35050.0),
        ]
        print("\n--- Control checks vs. Instructor Control workbook ---")
        all_ok = True
        for label, actual, expected in checks:
            ok = abs(actual - expected) < 0.01
            all_ok &= ok
            print(f"{'OK ' if ok else 'FAIL'}  {label}: {actual:,.2f} (expected {expected:,.2f})")
        if not all_ok:
            raise SystemExit("One or more control checks failed -- see above.")

        # ---- Export the review package ----
        job = get_job(ATBW_PATH)
        out_xlsx = OUT_DIR / "2025 Cedar & Slate Creative Instructor Answer Key.atbr.xlsx"
        export_review_package(conn, job=job, output_path=out_xlsx, performed_by=PREPARER)
        print(f"\nExported: {out_xlsx}")

    print(f"\nDone. Workup file: {ATBW_PATH}")


if __name__ == "__main__":
    main()
