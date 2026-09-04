"""
Binder hydration — inserts rows from a schema_version 2.0 __data snapshot
into an already-created .atbw SQLite binder (the job row already exists).

Insert order respects FK constraints:
  accounts → tax_lines → mappings → journal_entries → journal_entry_lines → notes
"""
from __future__ import annotations

import datetime


def hydrate_binder(conn, data: dict) -> None:
    """
    Populate an empty binder from a schema_version 2.0 __data snapshot.
    Uses INSERT OR IGNORE so re-runs are idempotent.
    """
    now = _utcnow()

    for a in data.get("accounts", []):
        conn.execute(
            """
            INSERT OR IGNORE INTO accounts
              (account_id, job_id, account_number, account_name, account_type,
               pbc_balance, normal_balance, source_row, is_mapped, flag,
               sort_order, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                a["account_id"], a["job_id"],
                a.get("account_number"),
                a["account_name"], a["account_type"],
                a.get("pbc_balance", 0.0),
                a.get("normal_balance", "Debit"),
                a.get("source_row"),
                a.get("is_mapped", 0),
                a.get("flag"),
                a.get("sort_order"),
                a.get("created_at") or now,
                a.get("updated_at") or now,
            ),
        )

    for tl in data.get("tax_lines", []):
        # category may be missing on exports made before this field existed,
        # or carrying a coarse pre-split value ('asset'/'liability') from
        # before the current_asset/fixed_asset/other_asset and current_
        # liability/noncurrent_liability split — derive fresh in both cases
        # rather than importing a blank or stale value.
        from atbworkup.data.tax_line_categories import classify_section, LEGACY_COARSE_CATEGORIES
        category = tl.get("category") or ""
        if not category or category in LEGACY_COARSE_CATEGORIES:
            category = classify_section(tl["financial_statement"], tl.get("section", ""))
        conn.execute(
            """
            INSERT OR IGNORE INTO tax_lines
              (tax_line_id, entity_type, financial_statement, section,
               section_sort_order, line_code, line_name, sort_order,
               is_active, tax_year, category)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                tl["tax_line_id"], tl["entity_type"], tl["financial_statement"],
                tl.get("section", ""),
                tl.get("section_sort_order", 0),
                tl["line_code"], tl["line_name"], tl["sort_order"],
                tl.get("is_active", 1),
                tl.get("tax_year"),
                category,
            ),
        )

    for m in data.get("mappings", []):
        conn.execute(
            """
            INSERT OR IGNORE INTO mappings
              (mapping_id, account_id, job_id, tax_line_id, section_id,
               mapped_by, mapped_at, notes)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                m["mapping_id"], m["account_id"], m["job_id"],
                m.get("tax_line_id"),
                m.get("section_id"),
                m.get("mapped_by", "preparer"),
                m.get("mapped_at") or now,
                m.get("notes"),
            ),
        )

    for e in data.get("entries", []):
        conn.execute(
            """
            INSERT OR IGNORE INTO journal_entries
              (aje_id, job_id, entry_type, entry_number, description,
               originated_by, originated_at, is_balanced, status, package_version,
               reviewer_signoff_by, reviewer_signoff_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                e["aje_id"], e["job_id"],
                e["entry_type"], e["entry_number"], e["description"],
                e.get("originated_by", "preparer"),
                e.get("originated_at") or now,
                e.get("is_balanced", 0),
                e.get("status", "Open"),
                e.get("package_version"),
                e.get("reviewer_signoff_by"),
                e.get("reviewer_signoff_at"),
            ),
        )

    for ln in data.get("entry_lines", []):
        conn.execute(
            """
            INSERT OR IGNORE INTO journal_entry_lines
              (line_id, aje_id, account_id, amount, memo, sort_order)
            VALUES (?,?,?,?,?,?)
            """,
            (
                ln["line_id"], ln["aje_id"], ln["account_id"],
                ln["amount"],
                ln.get("memo"),
                ln.get("sort_order", 0),
            ),
        )

    for n in data.get("notes", []):
        conn.execute(
            """
            INSERT OR IGNORE INTO notes
              (note_id, job_id, note_type, linked_to_type, linked_to_id,
               body, created_by, created_at, status,
               cleared_by, cleared_at, resolved_by, resolved_at, package_version)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                n["note_id"], n["job_id"],
                n.get("note_type", "preparer"),
                n.get("linked_to_type"),
                n.get("linked_to_id"),
                n["body"], n["created_by"],
                n.get("created_at") or now,
                n.get("status", "Open"),
                n.get("cleared_by"),
                n.get("cleared_at"),
                n.get("resolved_by"),
                n.get("resolved_at"),
                n.get("package_version"),
            ),
        )

    # account_groups before members (FK); export orders by sort_order so parents precede children
    for g in data.get("account_groups", []):
        conn.execute(
            """
            INSERT OR IGNORE INTO account_groups
              (group_id, job_id, name, parent_id, sort_order, created_at)
            VALUES (?,?,?,?,?,?)
            """,
            (
                g["group_id"], g["job_id"], g["name"],
                g.get("parent_id"),
                g.get("sort_order", 0),
                g.get("created_at") or now,
            ),
        )

    for m in data.get("account_group_members", []):
        conn.execute(
            "INSERT OR IGNORE INTO account_group_members (group_id, account_id) VALUES (?,?)",
            (m["group_id"], m["account_id"]),
        )

    for wl in data.get("workpaper_lines", []):
        conn.execute(
            """INSERT OR IGNORE INTO workpaper_lines
              (wp_line_id, job_id, workpaper, description, amount,
               line_type, sort_order, created_at)
            VALUES (?,?,?,?,?,?,?,?)""",
            (
                wl["wp_line_id"], wl["job_id"],
                wl["workpaper"], wl["description"],
                wl.get("amount", 0.0),
                wl.get("line_type"),
                wl.get("sort_order", 0),
                wl.get("created_at") or now,
            ),
        )

    for cm in data.get("consolidation_members", []):
        conn.execute(
            """
            INSERT OR IGNORE INTO consolidation_members
              (member_id, job_id, member_name, member_code, file_path,
               member_type, sort_order, created_at)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                cm["member_id"], cm["job_id"],
                cm["member_name"],
                cm.get("member_code", ""),
                cm["file_path"],
                cm.get("member_type", "subsidiary"),
                cm.get("sort_order", 0),
                cm.get("created_at") or now,
            ),
        )

    # consolidation_entry_lines FK's to consolidation_members, so entries/lines
    # must be inserted after members exist.
    for ce in data.get("consolidation_entries", []):
        conn.execute(
            """
            INSERT OR IGNORE INTO consolidation_entries
              (entry_id, job_id, workpaper, entry_number, description,
               originated_by, originated_at, status)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                ce["entry_id"], ce["job_id"], ce["workpaper"], ce["entry_number"],
                ce.get("description", ""),
                ce.get("originated_by"),
                ce.get("originated_at") or now,
                ce.get("status", "Open"),
            ),
        )

    for cel in data.get("consolidation_entry_lines", []):
        conn.execute(
            """
            INSERT OR IGNORE INTO consolidation_entry_lines
              (line_id, entry_id, member_id, account_id, amount, memo, sort_order)
            VALUES (?,?,?,?,?,?,?)
            """,
            (
                cel["line_id"], cel["entry_id"], cel["member_id"], cel["account_id"],
                cel.get("amount", 0.0),
                cel.get("memo"),
                cel.get("sort_order", 0),
            ),
        )

    for cg in data.get("consolidation_account_groups", []):
        conn.execute(
            """
            INSERT OR IGNORE INTO consolidation_account_groups
              (group_id, job_id, name, parent_id, sort_order, created_at)
            VALUES (?,?,?,?,?,?)
            """,
            (
                cg["group_id"], cg["job_id"], cg["name"],
                cg.get("parent_id"),
                cg.get("sort_order", 0),
                cg.get("created_at") or now,
            ),
        )

    for cgm in data.get("consolidation_group_members", []):
        conn.execute(
            """
            INSERT OR IGNORE INTO consolidation_group_members
              (group_id, member_id, account_id)
            VALUES (?,?,?)
            """,
            (cgm["group_id"], cgm["member_id"], cgm["account_id"]),
        )


def _utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
