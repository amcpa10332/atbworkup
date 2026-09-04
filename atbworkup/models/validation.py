"""
Pre-export validation engine.

Each check returns a dict:
  {
    "label":   str,          # short display name
    "status":  "pass"|"fail"|"warn",
    "detail":  str,          # human-readable explanation
    "jump_to": str | None,   # "unmapped" | "journal_entries" | None
  }

All failures block export. Warnings are advisory only.
"""
from __future__ import annotations


def run_all(conn, job_id: str) -> list[dict]:
    checks = [
        _check_tb_balance,
        _check_all_accounts_mapped,
        _check_ajes_balanced,
        _check_rjes_balanced,
        _check_ftjes_balanced,
        _check_both_fs_have_accounts,
    ]
    return [c(conn, job_id) for c in checks]


def all_pass(results: list[dict]) -> bool:
    return all(r["status"] != "fail" for r in results)


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def _check_tb_balance(conn, job_id: str) -> dict:
    row = conn.execute(
        "SELECT COALESCE(SUM(pbc_balance), 0) FROM accounts WHERE job_id = ?",
        (job_id,),
    ).fetchone()
    total = round(row[0], 2)
    if abs(total) < 0.005:
        return _pass("Trial balance in balance")
    return _fail(
        "Trial balance is out of balance",
        f"PBC total = {total:+,.2f} (must be 0.00)",
        jump_to="unmapped",
    )


def _check_all_accounts_mapped(conn, job_id: str) -> dict:
    row = conn.execute(
        "SELECT COUNT(*) FROM accounts WHERE job_id = ? AND is_mapped = 0",
        (job_id,),
    ).fetchone()
    n = row[0]
    if n == 0:
        return _pass("All accounts mapped")
    return _fail(
        f"{n} unmapped account{'s' if n != 1 else ''}",
        "All accounts must be mapped to a tax line before export.",
        jump_to="unmapped",
    )


def _check_ajes_balanced(conn, job_id: str) -> dict:
    return _check_entry_type_balanced(conn, job_id, "AJE")


def _check_rjes_balanced(conn, job_id: str) -> dict:
    return _check_entry_type_balanced(conn, job_id, "RJE")


def _check_ftjes_balanced(conn, job_id: str) -> dict:
    return _check_entry_type_balanced(conn, job_id, "FTJE")


def _check_entry_type_balanced(conn, job_id: str, entry_type: str) -> dict:
    rows = conn.execute(
        """SELECT entry_number, is_balanced
           FROM journal_entries
           WHERE job_id = ? AND entry_type = ?""",
        (job_id, entry_type),
    ).fetchall()
    if not rows:
        return _pass(f"No {entry_type}s (nothing to check)")
    unbalanced = [r["entry_number"] for r in rows if not r["is_balanced"]]
    if not unbalanced:
        return _pass(f"All {entry_type}s balanced")
    return _fail(
        f"{len(unbalanced)} unbalanced {entry_type}{'s' if len(unbalanced) != 1 else ''}",
        "Unbalanced: " + ", ".join(unbalanced),
        jump_to="journal_entries",
    )


def _check_both_fs_have_accounts(conn, job_id: str) -> dict:
    row = conn.execute(
        """SELECT COUNT(DISTINCT tl.financial_statement)
           FROM accounts a
           JOIN mappings m  ON m.account_id = a.account_id
           JOIN tax_lines tl ON tl.tax_line_id = m.tax_line_id
           WHERE a.job_id = ?
             AND tl.financial_statement IN ('BalanceSheet','ProfitAndLoss')""",
        (job_id,),
    ).fetchone()
    n = row[0]
    if n >= 2:
        return _pass("Balance Sheet and P&L both have mapped accounts")
    missing = []
    if n == 0:
        missing = ["Balance Sheet", "Profit & Loss"]
    else:
        has = conn.execute(
            """SELECT DISTINCT tl.financial_statement
               FROM accounts a
               JOIN mappings m  ON m.account_id = a.account_id
               JOIN tax_lines tl ON tl.tax_line_id = m.tax_line_id
               WHERE a.job_id = ?""",
            (job_id,),
        ).fetchall()
        have = {r[0] for r in has}
        if "BalanceSheet"  not in have:
            missing.append("Balance Sheet")
        if "ProfitAndLoss" not in have:
            missing.append("Profit & Loss")
    return _fail(
        f"Missing mapped accounts: {', '.join(missing)}",
        "Both financial statements must have at least one mapped account.",
        jump_to="unmapped",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pass(label: str) -> dict:
    return {"label": label, "status": "pass", "detail": "", "jump_to": None}


def _fail(label: str, detail: str = "", jump_to: str | None = None) -> dict:
    return {"label": label, "status": "fail", "detail": detail, "jump_to": jump_to}


def _warn(label: str, detail: str = "", jump_to: str | None = None) -> dict:
    return {"label": label, "status": "warn", "detail": detail, "jump_to": jump_to}
