"""
Account-to-tax-line mapping operations.
"""
from __future__ import annotations

import datetime
import uuid


def get_tax_line_templates(settings_conn, entity_type: str) -> list[dict]:
    """Return all active tax line templates for an entity type, ordered for display."""
    rows = settings_conn.execute(
        """
        SELECT template_id, entity_type, financial_statement,
               section, section_sort_order, line_code, line_name, sort_order,
               category
        FROM tax_line_templates
        WHERE entity_type = ? AND is_active = 1
        ORDER BY
            CASE financial_statement WHEN 'BalanceSheet' THEN 0 ELSE 1 END,
            section_sort_order,
            sort_order
        """,
        (entity_type,),
    ).fetchall()
    return [dict(r) for r in rows]


def upsert_tax_line(conn, *, entity_type: str, financial_statement: str,
                    line_code: str, line_name: str, sort_order: int,
                    section: str = "", section_sort_order: int = 0,
                    category: str = "") -> str:
    """
    Ensure a tax line exists in the binder's tax_lines table.
    Matches on (entity_type, line_code). Returns the tax_line_id.
    """
    existing = conn.execute(
        "SELECT tax_line_id FROM tax_lines WHERE entity_type = ? AND line_code = ?",
        (entity_type, line_code),
    ).fetchone()
    if existing:
        return existing["tax_line_id"]

    from atbworkup.data.tax_line_categories import classify_section, LEGACY_COARSE_CATEGORIES
    if not category or category in LEGACY_COARSE_CATEGORIES:
        category = classify_section(financial_statement, section)

    tax_line_id = uuid.uuid4().hex
    conn.execute(
        """INSERT INTO tax_lines
               (tax_line_id, entity_type, financial_statement,
                section, section_sort_order,
                line_code, line_name, sort_order, is_active, category)
           VALUES (?,?,?,?,?,?,?,?,1,?)""",
        (tax_line_id, entity_type, financial_statement,
         section, section_sort_order,
         line_code, line_name, sort_order, category),
    )
    return tax_line_id


def map_accounts(conn, *, job_id: str, account_ids: list[str],
                 tax_line_id: str, mapped_by: str) -> None:
    """
    Map a list of accounts to a tax line.
    Replaces any existing mapping for each account (one mapping per account).
    Sets accounts.is_mapped = 1.
    """
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for account_id in account_ids:
        # remove prior mapping for this account if any
        conn.execute(
            "DELETE FROM mappings WHERE account_id = ? AND job_id = ?",
            (account_id, job_id),
        )
        conn.execute(
            """INSERT INTO mappings
                   (mapping_id, account_id, job_id, tax_line_id, mapped_by, mapped_at)
               VALUES (?,?,?,?,?,?)""",
            (uuid.uuid4().hex, account_id, job_id, tax_line_id, mapped_by, now),
        )
        conn.execute(
            "UPDATE accounts SET is_mapped = 1, updated_at = ? WHERE account_id = ?",
            (now, account_id),
        )


def get_mapping(conn, account_id: str) -> dict | None:
    """Return the current mapping for an account, or None."""
    row = conn.execute(
        """
        SELECT m.tax_line_id, tl.line_name, tl.financial_statement, tl.line_code
        FROM mappings m
        JOIN tax_lines tl ON tl.tax_line_id = m.tax_line_id
        WHERE m.account_id = ?
        """,
        (account_id,),
    ).fetchone()
    return dict(row) if row else None
