"""
Settings database — stores user profile, admin password hash, and tax line templates.
Lives at atbw_settings.db next to the application data directory.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3

# Placed beside the executable / in the user's app data folder.
# For dev, we use the project root.
_SETTINGS_PATH: Path | None = None


def get_settings_path() -> Path:
    if _SETTINGS_PATH is not None:
        return _SETTINGS_PATH
    from atbworkup.constants import APP_NAME
    import os
    import sys
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        base = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base / "atbw_settings.db"


def set_settings_path(path: Path) -> None:
    global _SETTINGS_PATH
    _SETTINGS_PATH = Path(path)


@contextmanager
def settings_connection():
    path = get_settings_path()
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


_SETTINGS_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_profile (
    profile_id   TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    initials     TEXT,
    email        TEXT,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS package_roles (
    job_id      TEXT NOT NULL,
    profile_id  TEXT NOT NULL,
    role        TEXT NOT NULL,
    set_at      TEXT NOT NULL,
    PRIMARY KEY (job_id, profile_id)
);

CREATE TABLE IF NOT EXISTS admin_config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tax_line_templates (
    template_id         TEXT PRIMARY KEY,
    entity_type         TEXT NOT NULL,
    financial_statement TEXT NOT NULL,
    section             TEXT NOT NULL DEFAULT '',
    section_sort_order  INTEGER NOT NULL DEFAULT 0,
    line_code           TEXT NOT NULL,
    line_name           TEXT NOT NULL,
    sort_order          INTEGER NOT NULL,
    is_active           INTEGER NOT NULL DEFAULT 1,
    template_name       TEXT NOT NULL DEFAULT '',
    is_builtin          INTEGER NOT NULL DEFAULT 1,
    category            TEXT NOT NULL DEFAULT ''
);
"""


def apply_settings_schema(conn) -> None:
    conn.executescript(_SETTINGS_SCHEMA)
    conn.commit()


def ensure_settings_db() -> None:
    """Create schema, migrate existing DB if needed, and seed defaults."""
    with settings_connection() as conn:
        apply_settings_schema(conn)
        reseed = _migrate_settings_schema(conn)
        count = conn.execute(
            "SELECT COUNT(*) FROM tax_line_templates"
        ).fetchone()[0]
        if count == 0 or reseed:
            if reseed:
                conn.execute("DELETE FROM tax_line_templates")
            _seed_default_templates(conn)


def _migrate_settings_schema(conn) -> bool:
    """
    Add any columns that exist in the current schema but not in the on-disk table.
    Returns True if a migration ran that requires re-seeding templates.
    """
    tlt_cols = {row[1] for row in conn.execute("PRAGMA table_info(tax_line_templates)")}
    reseed = False
    if "section" not in tlt_cols:
        conn.execute(
            "ALTER TABLE tax_line_templates ADD COLUMN section TEXT NOT NULL DEFAULT ''"
        )
        reseed = True
    if "section_sort_order" not in tlt_cols:
        conn.execute(
            "ALTER TABLE tax_line_templates ADD COLUMN section_sort_order INTEGER NOT NULL DEFAULT 0"
        )
        reseed = True
    if "template_name" not in tlt_cols:
        conn.execute(
            "ALTER TABLE tax_line_templates ADD COLUMN template_name TEXT NOT NULL DEFAULT ''"
        )
        reseed = True
    if "is_builtin" not in tlt_cols:
        conn.execute(
            "ALTER TABLE tax_line_templates ADD COLUMN is_builtin INTEGER NOT NULL DEFAULT 1"
        )
        reseed = True
    if "category" not in tlt_cols:
        conn.execute(
            "ALTER TABLE tax_line_templates ADD COLUMN category TEXT NOT NULL DEFAULT ''"
        )
        reseed = True
    else:
        # The Balance Sheet category taxonomy was later split into finer
        # buckets (current_asset / fixed_asset / other_asset, current_
        # liability / noncurrent_liability). Templates are just a static
        # built-in catalog (no user data), so re-seeding wholesale is the
        # simplest correct fix rather than patching rows in place.
        from atbworkup.data.tax_line_categories import LEGACY_COARSE_CATEGORIES
        placeholders = ",".join("?" * len(LEGACY_COARSE_CATEGORIES))
        stale = conn.execute(
            f"SELECT 1 FROM tax_line_templates WHERE category IN ({placeholders}) LIMIT 1",
            tuple(LEGACY_COARSE_CATEGORIES),
        ).fetchone()
        if stale:
            reseed = True

    profile_cols = {row[1] for row in conn.execute("PRAGMA table_info(user_profile)")}
    if "initials" not in profile_cols:
        conn.execute("ALTER TABLE user_profile ADD COLUMN initials TEXT")

    return reseed


# ── User profile & role helpers ──────────────────────────────────────────────

import datetime as _dt
import uuid as _uuid


def _utcnow_s() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def has_profile() -> bool:
    with settings_connection() as conn:
        return conn.execute("SELECT 1 FROM user_profile LIMIT 1").fetchone() is not None


def get_active_profile() -> dict | None:
    with settings_connection() as conn:
        row = conn.execute("SELECT * FROM user_profile LIMIT 1").fetchone()
        return dict(row) if row else None


def save_profile(display_name: str, initials: str, email: str | None = None) -> None:
    with settings_connection() as conn:
        existing = conn.execute(
            "SELECT profile_id FROM user_profile LIMIT 1"
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE user_profile SET display_name=?, initials=?, email=? WHERE profile_id=?",
                (display_name, initials, email, existing["profile_id"]),
            )
        else:
            conn.execute(
                "INSERT INTO user_profile (profile_id, display_name, initials, email, created_at) "
                "VALUES (?,?,?,?,?)",
                (_uuid.uuid4().hex, display_name, initials, email, _utcnow_s()),
            )


def get_role_for_job(job_id: str) -> str | None:
    profile = get_active_profile()
    if not profile:
        return None
    with settings_connection() as conn:
        row = conn.execute(
            "SELECT role FROM package_roles WHERE job_id=? AND profile_id=?",
            (job_id, profile["profile_id"]),
        ).fetchone()
        return row["role"] if row else None


def set_role_for_job(job_id: str, role: str) -> None:
    profile = get_active_profile()
    if not profile:
        return
    with settings_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO package_roles (job_id, profile_id, role, set_at) "
            "VALUES (?,?,?,?)",
            (job_id, profile["profile_id"], role, _utcnow_s()),
        )


def _seed_default_templates(conn) -> None:
    import uuid
    from atbworkup.data.tax_line_seeds import DEFAULT_TAX_LINES, TEMPLATE_DISPLAY_NAMES
    from atbworkup.data.tax_line_categories import classify_section
    conn.executemany(
        """INSERT INTO tax_line_templates
               (template_id, entity_type, financial_statement,
                section, section_sort_order, line_code, line_name, sort_order,
                template_name, is_builtin, category)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        [
            (
                uuid.uuid4().hex,
                et, fs, sec, sec_sort, code, name, order,
                TEMPLATE_DISPLAY_NAMES.get(et, et),
                1,
                classify_section(fs, sec),
            )
            for et, fs, sec, sec_sort, code, name, order in DEFAULT_TAX_LINES
        ],
    )


# ── Template CRUD ─────────────────────────────────────────────────────────────

def list_templates() -> list[dict]:
    """
    Return one row per (entity_type, template_name, is_builtin) combination.
    Sorted: built-in first (alphabetically), then custom alphabetically.
    """
    with settings_connection() as conn:
        rows = conn.execute(
            """SELECT DISTINCT entity_type, template_name, is_builtin
               FROM tax_line_templates
               ORDER BY is_builtin DESC, template_name"""
        ).fetchall()
        return [dict(r) for r in rows]


def get_template_lines(entity_type: str) -> list[dict]:
    """Return all active template lines for *entity_type*, ordered for display."""
    with settings_connection() as conn:
        rows = conn.execute(
            """SELECT * FROM tax_line_templates
               WHERE entity_type = ? AND is_active = 1
               ORDER BY financial_statement, section_sort_order, sort_order""",
            (entity_type,),
        ).fetchall()
        return [dict(r) for r in rows]


def upsert_template_line(
    entity_type: str,
    financial_statement: str,
    section: str,
    section_sort_order: int,
    line_code: str,
    line_name: str,
    sort_order: int,
    template_name: str = "",
    is_builtin: int = 0,
    template_id: str | None = None,
) -> str:
    """Insert or replace a single template line. Returns template_id."""
    import uuid as _uuid_mod
    tid = template_id or _uuid_mod.uuid4().hex
    with settings_connection() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO tax_line_templates
                 (template_id, entity_type, financial_statement, section,
                  section_sort_order, line_code, line_name, sort_order,
                  is_active, template_name, is_builtin)
               VALUES (?,?,?,?,?,?,?,?,1,?,?)""",
            (tid, entity_type, financial_statement, section,
             section_sort_order, line_code, line_name, sort_order,
             template_name, is_builtin),
        )
    return tid


def delete_template(entity_type: str) -> None:
    """Delete all template lines for *entity_type*."""
    with settings_connection() as conn:
        conn.execute(
            "DELETE FROM tax_line_templates WHERE entity_type = ?",
            (entity_type,),
        )


def rename_template_line(template_id: str, new_line_name: str) -> None:
    with settings_connection() as conn:
        conn.execute(
            "UPDATE tax_line_templates SET line_name = ? WHERE template_id = ?",
            (new_line_name, template_id),
        )


def add_custom_line(
    entity_type: str,
    financial_statement: str,
    section: str,
    section_sort_order: int,
    line_code: str,
    line_name: str,
    after_sort_order: int,
    template_name: str = "",
) -> str:
    """Insert a new custom (is_builtin=0) line after *after_sort_order*."""
    return upsert_template_line(
        entity_type=entity_type,
        financial_statement=financial_statement,
        section=section,
        section_sort_order=section_sort_order,
        line_code=line_code,
        line_name=line_name,
        sort_order=after_sort_order + 5,
        template_name=template_name,
        is_builtin=0,
    )


# ── Legacy placeholder so old imports don't crash ────────────────────────────
_DEFAULT_TAX_LINES = [
    # ── 1120-S ──────────────────────────────────────────────────────────
    # Balance Sheet
    ("1120S", "BalanceSheet",  "Current Assets",          10,  "BS-01",  "Cash",                        10),
    ("1120S", "BalanceSheet",  "Current Assets",          10,  "BS-02",  "Accounts Receivable",         20),
    ("1120S", "BalanceSheet",  "Current Assets",          10,  "BS-03",  "Other Current Assets",        30),
    ("1120S", "BalanceSheet",  "Other Assets",            20,  "BS-04",  "Loans to Shareholders",       10),
    ("1120S", "BalanceSheet",  "Other Assets",            20,  "BS-05",  "Fixed Assets - Net",          20),
    ("1120S", "BalanceSheet",  "Other Assets",            20,  "BS-06",  "Other Assets",                30),
    ("1120S", "BalanceSheet",  "Current Liabilities",     30,  "BS-07",  "Accounts Payable",            10),
    ("1120S", "BalanceSheet",  "Current Liabilities",     30,  "BS-08",  "Other Current Liabilities",   20),
    ("1120S", "BalanceSheet",  "Long-Term Liabilities",   40,  "BS-09",  "Loans from Shareholders",     10),
    ("1120S", "BalanceSheet",  "Long-Term Liabilities",   40,  "BS-10",  "Long-Term Liabilities",       20),
    ("1120S", "BalanceSheet",  "Shareholders' Equity",    50,  "BS-11",  "Capital Stock",               10),
    ("1120S", "BalanceSheet",  "Shareholders' Equity",    50,  "BS-12",  "Additional Paid-In Capital",  20),
    ("1120S", "BalanceSheet",  "Shareholders' Equity",    50,  "BS-13",  "Retained Earnings",           30),
    ("1120S", "BalanceSheet",  "Shareholders' Equity",    50,  "BS-14",  "Distributions",               40),
    # Income Statement
    ("1120S", "ProfitAndLoss", "Revenue",                 10,  "PL-01",  "Gross Receipts / Sales",      10),
    ("1120S", "ProfitAndLoss", "Revenue",                 10,  "PL-02",  "Returns & Allowances",        20),
    ("1120S", "ProfitAndLoss", "Revenue",                 10,  "PL-15",  "Other Income",                30),
    ("1120S", "ProfitAndLoss", "Cost of Goods Sold",      20,  "PL-03",  "Cost of Goods Sold",          10),
    ("1120S", "ProfitAndLoss", "Deductions",              30,  "PL-04",  "Compensation of Officers",    10),
    ("1120S", "ProfitAndLoss", "Deductions",              30,  "PL-05",  "Salaries & Wages",            20),
    ("1120S", "ProfitAndLoss", "Deductions",              30,  "PL-06",  "Repairs & Maintenance",       30),
    ("1120S", "ProfitAndLoss", "Deductions",              30,  "PL-07",  "Bad Debts",                   40),
    ("1120S", "ProfitAndLoss", "Deductions",              30,  "PL-08",  "Rent",                        50),
    ("1120S", "ProfitAndLoss", "Deductions",              30,  "PL-09",  "Taxes & Licenses",            60),
    ("1120S", "ProfitAndLoss", "Deductions",              30,  "PL-10",  "Interest Expense",            70),
    ("1120S", "ProfitAndLoss", "Deductions",              30,  "PL-11",  "Depreciation",                80),
    ("1120S", "ProfitAndLoss", "Deductions",              30,  "PL-12",  "Advertising",                 90),
    ("1120S", "ProfitAndLoss", "Deductions",              30,  "PL-13",  "Employee Benefits",          100),
    ("1120S", "ProfitAndLoss", "Deductions",              30,  "PL-14",  "Other Deductions",           110),

    # ── 1065 ────────────────────────────────────────────────────────────
    ("1065",  "BalanceSheet",  "Current Assets",          10,  "BS-01",  "Cash",                        10),
    ("1065",  "BalanceSheet",  "Current Assets",          10,  "BS-02",  "Accounts Receivable",         20),
    ("1065",  "BalanceSheet",  "Current Assets",          10,  "BS-03",  "Other Current Assets",        30),
    ("1065",  "BalanceSheet",  "Other Assets",            20,  "BS-04",  "Partner Loans Receivable",    10),
    ("1065",  "BalanceSheet",  "Other Assets",            20,  "BS-05",  "Fixed Assets - Net",          20),
    ("1065",  "BalanceSheet",  "Other Assets",            20,  "BS-06",  "Other Assets",                30),
    ("1065",  "BalanceSheet",  "Current Liabilities",     30,  "BS-07",  "Accounts Payable",            10),
    ("1065",  "BalanceSheet",  "Current Liabilities",     30,  "BS-08",  "Other Current Liabilities",   20),
    ("1065",  "BalanceSheet",  "Long-Term Liabilities",   40,  "BS-09",  "Partner Loans Payable",       10),
    ("1065",  "BalanceSheet",  "Long-Term Liabilities",   40,  "BS-10",  "Long-Term Liabilities",       20),
    ("1065",  "BalanceSheet",  "Partners' Capital",       50,  "BS-11",  "Partners' Capital",           10),
    ("1065",  "BalanceSheet",  "Partners' Capital",       50,  "BS-12",  "Distributions",               20),
    ("1065",  "ProfitAndLoss", "Revenue",                 10,  "PL-01",  "Gross Receipts / Sales",      10),
    ("1065",  "ProfitAndLoss", "Revenue",                 10,  "PL-11",  "Other Income",                20),
    ("1065",  "ProfitAndLoss", "Cost of Goods Sold",      20,  "PL-02",  "Cost of Goods Sold",          10),
    ("1065",  "ProfitAndLoss", "Deductions",              30,  "PL-03",  "Guaranteed Payments",         10),
    ("1065",  "ProfitAndLoss", "Deductions",              30,  "PL-04",  "Salaries & Wages",            20),
    ("1065",  "ProfitAndLoss", "Deductions",              30,  "PL-05",  "Repairs & Maintenance",       30),
    ("1065",  "ProfitAndLoss", "Deductions",              30,  "PL-06",  "Rent",                        40),
    ("1065",  "ProfitAndLoss", "Deductions",              30,  "PL-07",  "Taxes & Licenses",            50),
    ("1065",  "ProfitAndLoss", "Deductions",              30,  "PL-08",  "Interest Expense",            60),
    ("1065",  "ProfitAndLoss", "Deductions",              30,  "PL-09",  "Depreciation",                70),
    ("1065",  "ProfitAndLoss", "Deductions",              30,  "PL-10",  "Other Deductions",            80),

    # ── 1120 ────────────────────────────────────────────────────────────
    ("1120",  "BalanceSheet",  "Current Assets",          10,  "BS-01",  "Cash",                        10),
    ("1120",  "BalanceSheet",  "Current Assets",          10,  "BS-02",  "Accounts Receivable",         20),
    ("1120",  "BalanceSheet",  "Current Assets",          10,  "BS-03",  "Inventories",                 30),
    ("1120",  "BalanceSheet",  "Current Assets",          10,  "BS-04",  "Other Current Assets",        40),
    ("1120",  "BalanceSheet",  "Other Assets",            20,  "BS-05",  "Loans to Shareholders",       10),
    ("1120",  "BalanceSheet",  "Other Assets",            20,  "BS-06",  "Fixed Assets - Net",          20),
    ("1120",  "BalanceSheet",  "Other Assets",            20,  "BS-07",  "Other Assets",                30),
    ("1120",  "BalanceSheet",  "Current Liabilities",     30,  "BS-08",  "Accounts Payable",            10),
    ("1120",  "BalanceSheet",  "Current Liabilities",     30,  "BS-09",  "Other Current Liabilities",   20),
    ("1120",  "BalanceSheet",  "Long-Term Liabilities",   40,  "BS-10",  "Long-Term Liabilities",       10),
    ("1120",  "BalanceSheet",  "Shareholders' Equity",    50,  "BS-11",  "Capital Stock",               10),
    ("1120",  "BalanceSheet",  "Shareholders' Equity",    50,  "BS-12",  "Additional Paid-In Capital",  20),
    ("1120",  "BalanceSheet",  "Shareholders' Equity",    50,  "BS-13",  "Retained Earnings",           30),
    ("1120",  "ProfitAndLoss", "Revenue",                 10,  "PL-01",  "Gross Receipts / Sales",      10),
    ("1120",  "ProfitAndLoss", "Revenue",                 10,  "PL-13",  "Dividends Received",          20),
    ("1120",  "ProfitAndLoss", "Revenue",                 10,  "PL-14",  "Other Income",                30),
    ("1120",  "ProfitAndLoss", "Cost of Goods Sold",      20,  "PL-02",  "Cost of Goods Sold",          10),
    ("1120",  "ProfitAndLoss", "Deductions",              30,  "PL-03",  "Compensation of Officers",    10),
    ("1120",  "ProfitAndLoss", "Deductions",              30,  "PL-04",  "Salaries & Wages",            20),
    ("1120",  "ProfitAndLoss", "Deductions",              30,  "PL-05",  "Repairs & Maintenance",       30),
    ("1120",  "ProfitAndLoss", "Deductions",              30,  "PL-06",  "Bad Debts",                   40),
    ("1120",  "ProfitAndLoss", "Deductions",              30,  "PL-07",  "Rent",                        50),
    ("1120",  "ProfitAndLoss", "Deductions",              30,  "PL-08",  "Taxes & Licenses",            60),
    ("1120",  "ProfitAndLoss", "Deductions",              30,  "PL-09",  "Interest Expense",            70),
    ("1120",  "ProfitAndLoss", "Deductions",              30,  "PL-10",  "Depreciation",                80),
    ("1120",  "ProfitAndLoss", "Deductions",              30,  "PL-11",  "Advertising",                 90),
    ("1120",  "ProfitAndLoss", "Deductions",              30,  "PL-12",  "Other Deductions",           100),

    # ── Schedule C ──────────────────────────────────────────────────────
    ("ScheduleC", "BalanceSheet",  "Assets",              10,  "BS-01",  "Cash",                        10),
    ("ScheduleC", "BalanceSheet",  "Assets",              10,  "BS-02",  "Accounts Receivable",         20),
    ("ScheduleC", "BalanceSheet",  "Assets",              10,  "BS-03",  "Other Assets",                30),
    ("ScheduleC", "BalanceSheet",  "Liabilities",         20,  "BS-04",  "Accounts Payable",            10),
    ("ScheduleC", "BalanceSheet",  "Liabilities",         20,  "BS-05",  "Other Liabilities",           20),
    ("ScheduleC", "BalanceSheet",  "Owner's Equity",      30,  "BS-06",  "Owner's Equity",              10),
    ("ScheduleC", "ProfitAndLoss", "Revenue",             10,  "PL-01",  "Gross Receipts / Sales",      10),
    ("ScheduleC", "ProfitAndLoss", "Revenue",             10,  "PL-02",  "Returns & Allowances",        20),
    ("ScheduleC", "ProfitAndLoss", "Revenue",             10,  "PL-22",  "Other Income",                30),
    ("ScheduleC", "ProfitAndLoss", "Cost of Goods Sold",  20,  "PL-03",  "Cost of Goods Sold",          10),
    ("ScheduleC", "ProfitAndLoss", "Expenses",            30,  "PL-04",  "Advertising",                 10),
    ("ScheduleC", "ProfitAndLoss", "Expenses",            30,  "PL-05",  "Car & Truck Expenses",        20),
    ("ScheduleC", "ProfitAndLoss", "Expenses",            30,  "PL-06",  "Commissions & Fees",          30),
    ("ScheduleC", "ProfitAndLoss", "Expenses",            30,  "PL-07",  "Contract Labor",              40),
    ("ScheduleC", "ProfitAndLoss", "Expenses",            30,  "PL-08",  "Depreciation",                50),
    ("ScheduleC", "ProfitAndLoss", "Expenses",            30,  "PL-09",  "Insurance",                   60),
    ("ScheduleC", "ProfitAndLoss", "Expenses",            30,  "PL-10",  "Interest Expense",            70),
    ("ScheduleC", "ProfitAndLoss", "Expenses",            30,  "PL-11",  "Legal & Professional",        80),
    ("ScheduleC", "ProfitAndLoss", "Expenses",            30,  "PL-12",  "Office Expense",              90),
    ("ScheduleC", "ProfitAndLoss", "Expenses",            30,  "PL-13",  "Rent / Lease",               100),
    ("ScheduleC", "ProfitAndLoss", "Expenses",            30,  "PL-14",  "Repairs & Maintenance",      110),
    ("ScheduleC", "ProfitAndLoss", "Expenses",            30,  "PL-15",  "Supplies",                   120),
    ("ScheduleC", "ProfitAndLoss", "Expenses",            30,  "PL-16",  "Taxes & Licenses",           130),
    ("ScheduleC", "ProfitAndLoss", "Expenses",            30,  "PL-17",  "Travel",                     140),
    ("ScheduleC", "ProfitAndLoss", "Expenses",            30,  "PL-18",  "Meals",                      150),
    ("ScheduleC", "ProfitAndLoss", "Expenses",            30,  "PL-19",  "Utilities",                  160),
    ("ScheduleC", "ProfitAndLoss", "Expenses",            30,  "PL-20",  "Wages",                      170),
    ("ScheduleC", "ProfitAndLoss", "Expenses",            30,  "PL-21",  "Other Expenses",             180),

    # ── 990 ─────────────────────────────────────────────────────────────
    ("990",  "BalanceSheet",  "Assets",                   10,  "BS-01",  "Cash & Cash Equivalents",          10),
    ("990",  "BalanceSheet",  "Assets",                   10,  "BS-02",  "Savings & Temporary Investments",  20),
    ("990",  "BalanceSheet",  "Assets",                   10,  "BS-03",  "Pledges & Grants Receivable",      30),
    ("990",  "BalanceSheet",  "Assets",                   10,  "BS-04",  "Accounts Receivable",              40),
    ("990",  "BalanceSheet",  "Assets",                   10,  "BS-05",  "Inventories & Prepaid Expenses",   50),
    ("990",  "BalanceSheet",  "Assets",                   10,  "BS-06",  "Land, Buildings & Equipment - Net",60),
    ("990",  "BalanceSheet",  "Assets",                   10,  "BS-07",  "Investments",                      70),
    ("990",  "BalanceSheet",  "Assets",                   10,  "BS-08",  "Other Assets",                     80),
    ("990",  "BalanceSheet",  "Liabilities",              20,  "BS-09",  "Accounts Payable",                 10),
    ("990",  "BalanceSheet",  "Liabilities",              20,  "BS-10",  "Grants Payable",                   20),
    ("990",  "BalanceSheet",  "Liabilities",              20,  "BS-11",  "Deferred Revenue",                 30),
    ("990",  "BalanceSheet",  "Liabilities",              20,  "BS-12",  "Other Liabilities",                40),
    ("990",  "BalanceSheet",  "Net Assets",               30,  "BS-13",  "Unrestricted Net Assets",          10),
    ("990",  "BalanceSheet",  "Net Assets",               30,  "BS-14",  "Temporarily Restricted Net Assets",20),
    ("990",  "BalanceSheet",  "Net Assets",               30,  "BS-15",  "Permanently Restricted Net Assets",30),
    ("990",  "ProfitAndLoss", "Revenue",                  10,  "PL-01",  "Contributions & Grants",           10),
    ("990",  "ProfitAndLoss", "Revenue",                  10,  "PL-02",  "Program Service Revenue",          20),
    ("990",  "ProfitAndLoss", "Revenue",                  10,  "PL-03",  "Investment Income",                30),
    ("990",  "ProfitAndLoss", "Revenue",                  10,  "PL-04",  "Other Revenue",                    40),
    ("990",  "ProfitAndLoss", "Expenses",                 20,  "PL-05",  "Grants & Similar Amounts Paid",    10),
    ("990",  "ProfitAndLoss", "Expenses",                 20,  "PL-06",  "Benefits Paid to Members",         20),
    ("990",  "ProfitAndLoss", "Expenses",                 20,  "PL-07",  "Salaries & Employee Benefits",     30),
    ("990",  "ProfitAndLoss", "Expenses",                 20,  "PL-08",  "Professional Fundraising Fees",    40),
    ("990",  "ProfitAndLoss", "Expenses",                 20,  "PL-09",  "Other Expenses",                   50),

    # ── 1041 ────────────────────────────────────────────────────────────
    ("1041", "BalanceSheet",  "Assets",                   10,  "BS-01",  "Cash",                             10),
    ("1041", "BalanceSheet",  "Assets",                   10,  "BS-02",  "Accounts Receivable",              20),
    ("1041", "BalanceSheet",  "Assets",                   10,  "BS-03",  "Investments",                      30),
    ("1041", "BalanceSheet",  "Assets",                   10,  "BS-04",  "Fixed Assets - Net",               40),
    ("1041", "BalanceSheet",  "Assets",                   10,  "BS-05",  "Other Assets",                     50),
    ("1041", "BalanceSheet",  "Liabilities",              20,  "BS-06",  "Accounts Payable",                 10),
    ("1041", "BalanceSheet",  "Liabilities",              20,  "BS-07",  "Other Liabilities",                20),
    ("1041", "BalanceSheet",  "Trust Equity",             30,  "BS-08",  "Trust / Estate Corpus",            10),
    ("1041", "BalanceSheet",  "Trust Equity",             30,  "BS-09",  "Accumulated Income",               20),
    ("1041", "ProfitAndLoss", "Income",                   10,  "PL-01",  "Interest Income",                  10),
    ("1041", "ProfitAndLoss", "Income",                   10,  "PL-02",  "Dividends",                        20),
    ("1041", "ProfitAndLoss", "Income",                   10,  "PL-03",  "Business Income",                  30),
    ("1041", "ProfitAndLoss", "Income",                   10,  "PL-04",  "Capital Gains / Losses",           40),
    ("1041", "ProfitAndLoss", "Income",                   10,  "PL-05",  "Rents, Royalties & Partnerships",  50),
    ("1041", "ProfitAndLoss", "Income",                   10,  "PL-06",  "Other Income",                     60),
    ("1041", "ProfitAndLoss", "Deductions",               20,  "PL-07",  "Interest Expense",                 10),
    ("1041", "ProfitAndLoss", "Deductions",               20,  "PL-08",  "Taxes",                            20),
    ("1041", "ProfitAndLoss", "Deductions",               20,  "PL-09",  "Fiduciary Fees",                   30),
    ("1041", "ProfitAndLoss", "Deductions",               20,  "PL-10",  "Attorney & Accounting Fees",       40),
    ("1041", "ProfitAndLoss", "Deductions",               20,  "PL-11",  "Other Deductions",                 50),
    ("1041", "ProfitAndLoss", "Deductions",               20,  "PL-12",  "Distributions to Beneficiaries",   60),
]
