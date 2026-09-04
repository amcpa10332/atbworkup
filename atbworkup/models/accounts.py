"""
Account queries and computed column calculations.

Sign convention: DR = positive, CR = negative throughout.
All computed values are derived at query time — never persisted.
"""
from __future__ import annotations

from atbworkup.db.connection import db_connection


# ---------------------------------------------------------------------------
# Column computation
# ---------------------------------------------------------------------------

def get_account_balances(conn, job_id: str) -> list[dict]:
    """
    Return every account with all seven computed columns.
    Joins journal_entry_lines to sum AJE/RJE/FTJE amounts per account.
    """
    rows = conn.execute(
        """
        SELECT
            a.account_id,
            a.account_number,
            a.account_name,
            a.account_type,
            a.pbc_balance,
            a.is_mapped,
            a.flag,
            a.sort_order,
            COALESCE(m.tax_line_id, NULL)             AS tax_line_id,
            COALESCE(m.section_id,  NULL)             AS section_id,
            COALESCE(tl.financial_statement, 'Unmapped') AS financial_statement,
            COALESCE(tl.section,    '')               AS section,
            COALESCE(tl.section_sort_order, 99999)    AS section_sort_order,
            COALESCE(tl.line_name,  'Unmapped')       AS line_name,
            COALESCE(tl.sort_order, 99999)            AS line_sort_order,
            COALESCE(tl.category,   '')               AS category,
            COALESCE(SUM(CASE WHEN je.entry_type = 'AJE'  THEN jel.amount ELSE 0 END), 0) AS aje_total,
            COALESCE(SUM(CASE WHEN je.entry_type = 'RJE'  THEN jel.amount ELSE 0 END), 0) AS rje_total,
            COALESCE(SUM(CASE WHEN je.entry_type = 'FTJE' THEN jel.amount ELSE 0 END), 0) AS ftje_total
        FROM accounts a
        LEFT JOIN mappings m       ON m.account_id = a.account_id
        LEFT JOIN tax_lines tl     ON tl.tax_line_id = m.tax_line_id
        LEFT JOIN journal_entry_lines jel ON jel.account_id = a.account_id
        LEFT JOIN journal_entries je      ON je.aje_id = jel.aje_id
                                         AND je.job_id = a.job_id
        WHERE a.job_id = ?
        GROUP BY a.account_id
        ORDER BY
            COALESCE(tl.section_sort_order, 99999),
            COALESCE(tl.sort_order, 99999),
            a.sort_order,
            a.account_number,
            a.account_name
        """,
        (job_id,),
    ).fetchall()

    result = []
    for r in rows:
        d = dict(r)
        pbc  = d["pbc_balance"]
        aje  = d["aje_total"]
        rje  = d["rje_total"]
        ftje = d["ftje_total"]
        adj   = round(pbc + aje,  2)
        final = round(adj + rje,  2)
        ftax  = round(final + ftje, 2)
        d.update(aje=round(aje, 2), adj=adj, rje=round(rje, 2),
                 final=final, ftje=round(ftje, 2), ftax=ftax)
        result.append(d)
    return result


def get_grouped_balances(conn, job_id: str) -> dict[str, list[dict]]:
    """
    Return accounts grouped by financial_statement then line_name.
    Keys: 'BalanceSheet', 'ProfitAndLoss', 'Unmapped'
    Each value is a list of account dicts (same shape as get_account_balances).
    """
    accounts = get_account_balances(conn, job_id)
    groups: dict[str, list[dict]] = {}
    for acct in accounts:
        key = acct["financial_statement"]
        groups.setdefault(key, []).append(acct)
    return groups


def create_account(
    conn,
    job_id: str,
    account_number: str,
    account_name: str,
    account_type: str,
    normal_balance: str,
    pbc_balance: float = 0.0,
) -> str:
    """Insert a new account and return its account_id.

    Raises ValueError if account_number is non-blank and already exists for this job.
    """
    import datetime
    from atbworkup.utils.ids import new_uuid
    if account_number:
        dup = conn.execute(
            "SELECT account_id FROM accounts WHERE job_id = ? AND account_number = ?",
            (job_id, account_number),
        ).fetchone()
        if dup:
            raise ValueError(
                f"Account number '{account_number}' already exists in this binder.\n"
                "Use a different number, or leave it blank."
            )
    account_id = new_uuid()
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # Sort after existing accounts by using a high sort_order
    max_sort = conn.execute(
        "SELECT COALESCE(MAX(sort_order), 0) FROM accounts WHERE job_id = ?", (job_id,)
    ).fetchone()[0]
    conn.execute(
        """INSERT INTO accounts
             (account_id, job_id, account_number, account_name, account_type,
              pbc_balance, normal_balance, is_mapped, sort_order, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,0,?,?,?)""",
        (account_id, job_id, account_number or None, account_name,
         account_type, pbc_balance, normal_balance, max_sort + 10, now, now),
    )
    return account_id


def update_account(
    conn,
    account_id: str,
    *,
    account_number: str | None = None,
    account_name: str | None = None,
    account_type: str | None = None,
    normal_balance: str | None = None,
    pbc_balance: float | None = None,
) -> None:
    """Update editable fields on an existing account. Pass only fields to change."""
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    updates: list[tuple] = []
    if account_number is not None:
        updates.append(("account_number", account_number or None))
    if account_name is not None:
        updates.append(("account_name", account_name))
    if account_type is not None:
        updates.append(("account_type", account_type))
    if normal_balance is not None:
        updates.append(("normal_balance", normal_balance))
    if pbc_balance is not None:
        updates.append(("pbc_balance", pbc_balance))
    if not updates:
        return
    set_clause = ", ".join(f"{col} = ?" for col, _ in updates) + ", updated_at = ?"
    values = [v for _, v in updates] + [now, account_id]
    conn.execute(f"UPDATE accounts SET {set_clause} WHERE account_id = ?", values)


def delete_accounts(conn, account_ids: list[str]) -> tuple[list[str], list[str]]:
    """
    Delete accounts that have no journal entry lines.

    Returns (deleted_names, blocked_names) where blocked_names are accounts
    that could not be deleted because they have JE lines referencing them.
    """
    deleted, blocked = [], []
    for aid in account_ids:
        row = conn.execute(
            "SELECT account_name FROM accounts WHERE account_id = ?", (aid,)
        ).fetchone()
        if not row:
            continue
        name = row["account_name"]

        je_count = conn.execute(
            "SELECT COUNT(*) FROM journal_entry_lines WHERE account_id = ?", (aid,)
        ).fetchone()[0]
        if je_count:
            blocked.append(name)
            continue

        # Safe to delete — clean dependent tables first
        conn.execute("DELETE FROM mappings WHERE account_id = ?", (aid,))
        conn.execute("DELETE FROM account_group_members WHERE account_id = ?", (aid,))
        conn.execute(
            "DELETE FROM prior_year_balances WHERE account_id = ?", (aid,)
        )
        conn.execute(
            "DELETE FROM notes WHERE linked_to_id = ? AND linked_to_type = 'account'",
            (aid,),
        )
        conn.execute("DELETE FROM accounts WHERE account_id = ?", (aid,))
        deleted.append(name)
    return deleted, blocked


def set_flag(conn, account_id: str, flag: str | None) -> None:
    """Set or clear the flag on an account."""
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        "UPDATE accounts SET flag = ?, updated_at = ? WHERE account_id = ?",
        (flag, now, account_id),
    )
