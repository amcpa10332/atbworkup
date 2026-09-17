"""
Write / reimport a ParseResult into the accounts table of an open .btaw file.
Called after the user confirms the import wizard.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field

from blueprinttb.importer.tb_parser import ParseResult, normalize_account_number
from blueprinttb.models.activity import log_activity
from blueprinttb.utils.ids import new_uuid


@dataclass
class ReimportResult:
    updated: int     # accounts whose pbc_balance was changed
    added: int       # new accounts not previously in the binder
    unchanged: int   # accounts that matched and had no balance change
    flagged: int     # accounts in DB but absent from new TB (flagged "missing")


@dataclass
class ImportStats:
    inserted:            int
    auto_mapped:         int = 0
    unrecognized_codes:  list[str] = field(default_factory=list)


def write_accounts(conn, *, job_id: str, result: ParseResult, performed_by: str) -> ImportStats:
    """
    Insert accounts from `result` into the open connection.
    All inserted accounts start is_mapped = 0; any account whose
    ParsedAccount.tax_line_code matches a known tax line for this job's
    entity type (see tb_parser.parse_accounts' grouping_col) is then
    immediately mapped, same as a manual mapping-workbench assignment.
    """
    now = _now()

    templates_by_code: dict[str, dict] = {}
    if any(a.tax_line_code for a in result.accounts):
        job_row = conn.execute(
            "SELECT entity_type FROM job WHERE job_id = ?", (job_id,)
        ).fetchone()
        entity_type = job_row["entity_type"] if job_row else ""
        from blueprinttb.db.settings import settings_connection, ensure_settings_db
        from blueprinttb.models.mappings import get_tax_line_templates
        ensure_settings_db()
        with settings_connection() as sconn:
            templates = get_tax_line_templates(sconn, entity_type)
        templates_by_code = {t["line_code"].strip().lower(): t for t in templates}

    stats = ImportStats(inserted=len(result.accounts))
    unrecognized: set[str] = set()

    for acct in result.accounts:
        account_type = _guess_type(acct.pbc_balance)
        normal_balance = "Debit" if acct.pbc_balance >= 0 else "Credit"
        account_id = new_uuid()
        conn.execute(
            """
            INSERT INTO accounts (
                account_id, job_id, account_number, account_name,
                account_type, pbc_balance, normal_balance,
                source_row, is_mapped, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                account_id, job_id,
                acct.account_number or None,
                acct.account_name,
                account_type,
                acct.pbc_balance,
                normal_balance,
                acct.source_row,
                now, now,
            ),
        )

        code = acct.tax_line_code.strip().lower() if acct.tax_line_code else ""
        if not code:
            continue
        tmpl = templates_by_code.get(code)
        if tmpl is None:
            unrecognized.add(acct.tax_line_code.strip())
            continue

        from blueprinttb.models.mappings import upsert_tax_line, map_accounts
        tax_line_id = upsert_tax_line(
            conn,
            entity_type=entity_type,
            financial_statement=tmpl["financial_statement"],
            line_code=tmpl["line_code"],
            line_name=tmpl["line_name"],
            sort_order=tmpl["sort_order"],
            section=tmpl["section"],
            section_sort_order=tmpl["section_sort_order"],
            category=tmpl.get("category", ""),
        )
        map_accounts(conn, job_id=job_id, account_ids=[account_id],
                    tax_line_id=tax_line_id, mapped_by=performed_by)
        stats.auto_mapped += 1

    stats.unrecognized_codes = sorted(unrecognized)

    mapped_note = f", {stats.auto_mapped} auto-mapped from pre-mapped codes" if stats.auto_mapped else ""
    log_activity(
        conn,
        job_id=job_id,
        event_type="imported_tb",
        description=(
            f"Imported trial balance: {len(result.accounts)} accounts, "
            f"debits {result.total_debits:,.2f}, credits {result.total_credits:,.2f}"
            f"{mapped_note}"
        ),
        performed_by=performed_by,
    )

    return stats


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
    by_name: dict[str, list[dict]] = {}
    for row in existing:
        r = dict(row)
        if r["account_number"]:
            by_number[normalize_account_number(r["account_number"])] = r
        by_name.setdefault(r["account_name"].strip().lower(), []).append(r)

    matched_ids: set[str] = set()
    updated = added = unchanged = 0

    for acct in result.accounts:
        num = normalize_account_number(acct.account_number or "")
        name_key = acct.account_name.strip().lower()

        db_row = by_number.get(num) if num else None
        if db_row is None:
            # Only fall back to a name match when it's unambiguous -- two
            # existing accounts sharing a name would otherwise let the
            # second one silently steal the first one's match.
            candidates = by_name.get(name_key, [])
            if len(candidates) == 1:
                db_row = candidates[0]

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
