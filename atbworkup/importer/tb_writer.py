"""
Write / reimport a ParseResult into the accounts table of an open .atbw file.
Called after the user confirms the import wizard.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass

from atbworkup.importer.tb_parser import ParseResult
from atbworkup.models.activity import log_activity
from atbworkup.utils.ids import new_uuid


@dataclass
class ReimportResult:
    updated: int     # accounts whose pbc_balance was changed
    added: int       # new accounts not previously in the binder
    unchanged: int   # accounts that matched and had no balance change
    flagged: int     # accounts in DB but absent from new TB (flagged "missing")


def write_accounts(conn, *, job_id: str, result: ParseResult, performed_by: str) -> int:
    """
    Insert accounts from `result` into the open connection.
    Returns the number of rows inserted.
    All inserted accounts have is_mapped = 0.
    """
    now = _now()

    for acct in result.accounts:
        account_type = _guess_type(acct.pbc_balance)
        normal_balance = "Debit" if acct.pbc_balance >= 0 else "Credit"
        conn.execute(
            """
            INSERT INTO accounts (
                account_id, job_id, account_number, account_name,
                account_type, pbc_balance, normal_balance,
                source_row, is_mapped, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                new_uuid(), job_id,
                acct.account_number or None,
                acct.account_name,
                account_type,
                acct.pbc_balance,
                normal_balance,
                acct.source_row,
                now, now,
            ),
        )

    log_activity(
        conn,
        job_id=job_id,
        event_type="imported_tb",
        description=(
            f"Imported trial balance: {len(result.accounts)} accounts, "
            f"debits {result.total_debits:,.2f}, credits {result.total_credits:,.2f}"
        ),
        performed_by=performed_by,
    )

    return len(result.accounts)


def reimport_accounts(
    conn,
    *,
    job_id: str,
    result: ParseResult,
    performed_by: str,
) -> ReimportResult:
    """
    Update PBC balances from a new TB export without disturbing JEs or mappings.

    Matching strategy (in priority order):
      1. account_number exact match (if both have a number)
      2. account_name exact match (case-insensitive)

    Accounts in the DB that have no match in the new TB are flagged "missing".
    Accounts in the new TB with no match are inserted as new accounts.
    """
    now = _now()

    # Build lookup from existing DB accounts
    existing = conn.execute(
        "SELECT account_id, account_number, account_name, pbc_balance, flag "
        "FROM accounts WHERE job_id = ?",
        (job_id,),
    ).fetchall()

    by_number: dict[str, dict] = {}
    by_name: dict[str, dict] = {}
    for row in existing:
        r = dict(row)
        if r["account_number"]:
            by_number[r["account_number"].strip()] = r
        by_name[r["account_name"].strip().lower()] = r

    matched_ids: set[str] = set()
    updated = added = unchanged = 0

    for acct in result.accounts:
        num = (acct.account_number or "").strip()
        name_key = acct.account_name.strip().lower()

        db_row = by_number.get(num) if num else None
        if db_row is None:
            db_row = by_name.get(name_key)

        if db_row is not None:
            matched_ids.add(db_row["account_id"])
            old_pbc = db_row["pbc_balance"]
            if abs(float(old_pbc) - float(acct.pbc_balance)) > 0.005:
                conn.execute(
                    "UPDATE accounts SET pbc_balance = ?, updated_at = ?, flag = NULL "
                    "WHERE account_id = ?",
                    (acct.pbc_balance, now, db_row["account_id"]),
                )
                updated += 1
            else:
                # Clear a stale "missing" flag if the account reappeared unchanged
                if db_row.get("flag") == "missing":
                    conn.execute(
                        "UPDATE accounts SET flag = NULL, updated_at = ? WHERE account_id = ?",
                        (now, db_row["account_id"]),
                    )
                unchanged += 1
        else:
            # New account not previously in the binder
            account_type = _guess_type(acct.pbc_balance)
            normal_balance = "Debit" if acct.pbc_balance >= 0 else "Credit"
            conn.execute(
                """INSERT INTO accounts (
                       account_id, job_id, account_number, account_name,
                       account_type, pbc_balance, normal_balance,
                       source_row, is_mapped, created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)""",
                (
                    new_uuid(), job_id,
                    acct.account_number or None,
                    acct.account_name,
                    account_type,
                    acct.pbc_balance,
                    normal_balance,
                    acct.source_row,
                    now, now,
                ),
            )
            added += 1

    # Flag accounts that disappeared from the new TB
    flagged = 0
    for row in existing:
        if row["account_id"] not in matched_ids and row["flag"] != "missing":
            conn.execute(
                "UPDATE accounts SET flag = 'missing', updated_at = ? WHERE account_id = ?",
                (now, row["account_id"]),
            )
            flagged += 1

    log_activity(
        conn,
        job_id=job_id,
        event_type="reimported_tb",
        description=(
            f"Reimported trial balance: {updated} updated, {added} new, "
            f"{unchanged} unchanged, {flagged} flagged missing"
        ),
        performed_by=performed_by,
    )

    return ReimportResult(
        updated=updated, added=added, unchanged=unchanged, flagged=flagged
    )


def _guess_type(balance: float) -> str:
    return "Asset" if balance >= 0 else "Liability"


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
