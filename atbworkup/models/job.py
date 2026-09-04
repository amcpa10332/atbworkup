"""
Job model: create, open, and read workup files.
All functions that modify the database accept an open connection
so callers control transaction boundaries.
"""
from __future__ import annotations

import datetime
from pathlib import Path

from atbworkup.constants import APP_VERSION, SCHEMA_VERSION
from atbworkup.db.connection import db_connection
from atbworkup.db.schema import apply_schema
from atbworkup.models.activity import log_activity
from atbworkup.utils.ids import new_uuid
from atbworkup.utils.naming import suggested_filename


def create_workup(path: str | Path, metadata: dict,
                  job_id: str | None = None) -> str:
    """
    Create a new .atbw file at `path`, apply schema, insert job row,
    and write a created_workup activity log entry.

    Returns the job_id.  Pass job_id explicitly to preserve an existing ID
    (e.g. when re-hydrating from a .atbr.xlsx package).

    metadata keys (all TEXT unless noted):
        client_name, entity_name, tax_year (int), entity_type,
        prepared_by, reviewer (opt), workpaper_folder (opt),
        accounting_system (opt)
    """
    path = Path(path)
    job_id = job_id or new_uuid()
    now = _utcnow()

    with db_connection(path) as conn:
        apply_schema(conn)
        conn.execute(
            """
            INSERT INTO job (
                job_id, client_name, entity_name, tax_year, entity_type,
                prepared_by, reviewer, workpaper_folder, accounting_system,
                status, workflow_version, schema_version, app_version,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?,
                      'Preparation in Progress', 1, ?, ?, ?, ?)
            """,
            (
                job_id,
                metadata["client_name"],
                metadata["entity_name"],
                int(metadata["tax_year"]),
                metadata["entity_type"],
                metadata["prepared_by"],
                metadata.get("reviewer"),
                metadata.get("workpaper_folder"),
                metadata.get("accounting_system"),
                SCHEMA_VERSION,
                APP_VERSION,
                now,
                now,
            ),
        )
        log_activity(
            conn,
            job_id=job_id,
            event_type="created_workup",
            description=f"Created workup for {metadata['client_name']} {metadata['tax_year']}",
            performed_by=metadata["prepared_by"],
        )

    return job_id


def open_workup(path: str | Path, performed_by: str) -> dict:
    """
    Open an existing .atbw file, validate it, log the open event,
    and return the job metadata as a dict.

    Raises ValueError if the file is not a valid workup.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    with db_connection(path) as conn:
        row = conn.execute("SELECT * FROM job LIMIT 1").fetchone()
        if row is None:
            raise ValueError("File is not a valid workup: no job record found.")
        job = dict(row)
        _migrate_binder(conn)
        log_activity(
            conn,
            job_id=job["job_id"],
            event_type="opened_workup",
            description=f"Opened workup for {job['client_name']} {job['tax_year']}",
            performed_by=performed_by,
        )

    return job


def transition_status(conn, job_id: str, new_status: str,
                      performed_by: str) -> int:
    """
    Advance the job's workflow_status and increment workflow_version.
    Returns the new version number.
    """
    now = _utcnow()
    row = conn.execute(
        "SELECT status, workflow_version FROM job WHERE job_id = ?", (job_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"Job {job_id} not found")
    old_status = row[0]
    new_version = (row[1] or 1) + 1

    conn.execute(
        """UPDATE job SET status = ?, workflow_version = ?, updated_at = ?
           WHERE job_id = ?""",
        (new_status, new_version, now, job_id),
    )
    log_activity(
        conn,
        job_id=job_id,
        event_type="status_changed",
        description=f"Status: {old_status} → {new_status}",
        performed_by=performed_by,
    )
    return new_version


def _migrate_binder(conn) -> None:
    """Add any columns introduced after the binder was first created."""
    tax_line_cols = {
        row[1] for row in conn.execute("PRAGMA table_info(tax_lines)")
    }
    if "section" not in tax_line_cols:
        conn.execute(
            "ALTER TABLE tax_lines ADD COLUMN section TEXT NOT NULL DEFAULT ''"
        )
    if "section_sort_order" not in tax_line_cols:
        conn.execute(
            "ALTER TABLE tax_lines ADD COLUMN section_sort_order INTEGER NOT NULL DEFAULT 0"
        )
    if "category" not in tax_line_cols:
        conn.execute("ALTER TABLE tax_lines ADD COLUMN category TEXT NOT NULL DEFAULT ''")
        # Backfill existing tax lines so old binders benefit immediately
        # instead of falling back to runtime section-name matching forever.
        from atbworkup.data.tax_line_categories import classify_section
        rows = conn.execute(
            "SELECT tax_line_id, financial_statement, section FROM tax_lines"
        ).fetchall()
        for row in rows:
            category = classify_section(row["financial_statement"], row["section"])
            conn.execute(
                "UPDATE tax_lines SET category = ? WHERE tax_line_id = ?",
                (category, row["tax_line_id"]),
            )
    else:
        # category column already existed, but the Balance Sheet taxonomy
        # was later split into finer buckets (current_asset / fixed_asset /
        # other_asset, current_liability / noncurrent_liability) to support
        # GAAP-style report subtotals. Re-derive ONLY rows still carrying
        # the old coarse 'asset'/'liability' values — never touches a row
        # that's already on the new scheme (which may have been manually
        # overridden via the groupings editor).
        from atbworkup.data.tax_line_categories import classify_section, LEGACY_COARSE_CATEGORIES
        placeholders = ",".join("?" * len(LEGACY_COARSE_CATEGORIES))
        rows = conn.execute(
            f"SELECT tax_line_id, financial_statement, section FROM tax_lines "
            f"WHERE category IN ({placeholders})",
            tuple(LEGACY_COARSE_CATEGORIES),
        ).fetchall()
        for row in rows:
            category = classify_section(row["financial_statement"], row["section"])
            conn.execute(
                "UPDATE tax_lines SET category = ? WHERE tax_line_id = ?",
                (category, row["tax_line_id"]),
            )

    je_cols = {row[1] for row in conn.execute("PRAGMA table_info(journal_entries)")}
    if "reviewer_signoff_by" not in je_cols:
        conn.execute("ALTER TABLE journal_entries ADD COLUMN reviewer_signoff_by TEXT")
    if "reviewer_signoff_at" not in je_cols:
        conn.execute("ALTER TABLE journal_entries ADD COLUMN reviewer_signoff_at TEXT")

    activity_cols = {row[1] for row in conn.execute("PRAGMA table_info(activity_log)")}
    if "prev_hash" not in activity_cols:
        conn.execute("ALTER TABLE activity_log ADD COLUMN prev_hash TEXT")
        conn.execute("ALTER TABLE activity_log ADD COLUMN row_hash TEXT")
        # Backfill: chain every existing row in insertion order so binders
        # created before the hash-chain feature still get real, verifiable
        # hashes going forward (tamper-evidence starts from this point on).
        from atbworkup.models.activity import compute_row_hash, GENESIS_HASH
        rows = conn.execute(
            """SELECT activity_id, job_id, event_type, entity_type, entity_id,
                      description, performed_by, performed_at, package_version,
                      metadata_json
               FROM activity_log ORDER BY job_id, rowid"""
        ).fetchall()
        prev_by_job: dict[str, str] = {}
        for row in rows:
            jid = row["job_id"]
            prev = prev_by_job.get(jid, GENESIS_HASH)
            row_hash = compute_row_hash(
                prev, jid, row["event_type"], row["entity_type"], row["entity_id"],
                row["description"], row["performed_by"], row["performed_at"],
                row["package_version"], row["metadata_json"],
            )
            conn.execute(
                "UPDATE activity_log SET prev_hash = ?, row_hash = ? WHERE activity_id = ?",
                (prev, row_hash, row["activity_id"]),
            )
            prev_by_job[jid] = row_hash

    job_cols = {row[1] for row in conn.execute("PRAGMA table_info(job)")}
    if "workflow_version" not in job_cols:
        conn.execute(
            "ALTER TABLE job ADD COLUMN workflow_version INTEGER NOT NULL DEFAULT 1"
        )
        # Migrate old status names to new ones
        conn.execute(
            "UPDATE job SET status = 'Preparation in Progress' "
            "WHERE status IN ('Draft', 'In Prep')"
        )
        conn.execute(
            "UPDATE job SET status = 'Ready for Review' "
            "WHERE status IN ('Ready for Review', 'Cleared for Review', "
            "                 'Ready for Final Review')"
        )
        conn.execute(
            "UPDATE job SET status = 'Clear Notes' "
            "WHERE status = 'Reviewer Notes'"
        )
        conn.execute(
            "UPDATE job SET status = 'Finalized' "
            "WHERE status = 'Final'"
        )

    existing_tables = {
        row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    if "prior_year_balances" not in existing_tables:
        conn.execute("""
            CREATE TABLE prior_year_balances (
                py_balance_id    TEXT PRIMARY KEY,
                job_id           TEXT NOT NULL REFERENCES job(job_id),
                account_id       TEXT REFERENCES accounts(account_id),
                section_id       TEXT REFERENCES sections(section_id),
                tax_line_id      TEXT,
                py_final_balance REAL,
                py_ftax_balance  REAL,
                source           TEXT NOT NULL DEFAULT 'manual',
                entered_at       TEXT NOT NULL
            )
        """)
    if "account_groups" not in existing_tables:
        conn.execute("""
            CREATE TABLE account_groups (
                group_id   TEXT PRIMARY KEY,
                job_id     TEXT NOT NULL REFERENCES job(job_id),
                name       TEXT NOT NULL,
                parent_id  TEXT REFERENCES account_groups(group_id),
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)
    if "account_group_members" not in existing_tables:
        conn.execute("""
            CREATE TABLE account_group_members (
                group_id   TEXT NOT NULL REFERENCES account_groups(group_id),
                account_id TEXT NOT NULL REFERENCES accounts(account_id),
                PRIMARY KEY (group_id, account_id)
            )
        """)
    if "workpaper_lines" not in existing_tables:
        conn.execute("""
            CREATE TABLE workpaper_lines (
                wp_line_id  TEXT PRIMARY KEY,
                job_id      TEXT NOT NULL REFERENCES job(job_id),
                workpaper   TEXT NOT NULL,
                description TEXT NOT NULL,
                amount      REAL NOT NULL DEFAULT 0,
                line_type   TEXT,
                sort_order  INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT NOT NULL
            )
        """)
    if "owners" not in existing_tables:
        conn.execute("""
            CREATE TABLE owners (
                owner_id      TEXT PRIMARY KEY,
                job_id        TEXT NOT NULL REFERENCES job(job_id),
                name          TEXT NOT NULL,
                tin           TEXT,
                ownership_pct REAL NOT NULL DEFAULT 0,
                sort_order    INTEGER NOT NULL DEFAULT 0,
                created_at    TEXT NOT NULL
            )
        """)
    if "consolidation_members" not in existing_tables:
        conn.execute("""
            CREATE TABLE consolidation_members (
                member_id   TEXT PRIMARY KEY,
                job_id      TEXT NOT NULL REFERENCES job(job_id),
                member_name TEXT NOT NULL,
                member_code TEXT NOT NULL DEFAULT '',
                file_path   TEXT NOT NULL,
                member_type TEXT NOT NULL DEFAULT 'subsidiary',
                sort_order  INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT NOT NULL
            )
        """)
    else:
        cm_cols = {row[1] for row in conn.execute("PRAGMA table_info(consolidation_members)")}
        if "member_code" not in cm_cols:
            conn.execute(
                "ALTER TABLE consolidation_members ADD COLUMN member_code TEXT NOT NULL DEFAULT ''"
            )
    if "consolidation_entries" not in existing_tables:
        conn.execute("""
            CREATE TABLE consolidation_entries (
                entry_id      TEXT PRIMARY KEY,
                job_id        TEXT NOT NULL REFERENCES job(job_id),
                workpaper     TEXT NOT NULL,
                entry_number  TEXT NOT NULL,
                description   TEXT NOT NULL DEFAULT '',
                originated_by TEXT,
                originated_at TEXT NOT NULL,
                status        TEXT NOT NULL DEFAULT 'Open'
            )
        """)
    if "consolidation_entry_lines" not in existing_tables:
        conn.execute("""
            CREATE TABLE consolidation_entry_lines (
                line_id    TEXT PRIMARY KEY,
                entry_id   TEXT NOT NULL REFERENCES consolidation_entries(entry_id),
                member_id  TEXT NOT NULL REFERENCES consolidation_members(member_id),
                account_id TEXT NOT NULL,
                amount     REAL NOT NULL DEFAULT 0,
                memo       TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0
            )
        """)
    if "consolidation_account_groups" not in existing_tables:
        conn.execute("""
            CREATE TABLE consolidation_account_groups (
                group_id   TEXT PRIMARY KEY,
                job_id     TEXT NOT NULL REFERENCES job(job_id),
                name       TEXT NOT NULL,
                parent_id  TEXT REFERENCES consolidation_account_groups(group_id),
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)
    if "consolidation_group_members" not in existing_tables:
        conn.execute("""
            CREATE TABLE consolidation_group_members (
                group_id   TEXT NOT NULL REFERENCES consolidation_account_groups(group_id),
                member_id  TEXT NOT NULL REFERENCES consolidation_members(member_id),
                account_id TEXT NOT NULL,
                PRIMARY KEY (group_id, member_id, account_id)
            )
        """)


def get_job(path: str | Path) -> dict:
    """Read job metadata without logging an open event."""
    path = Path(path)
    with db_connection(path) as conn:
        row = conn.execute("SELECT * FROM job LIMIT 1").fetchone()
        if row is None:
            raise ValueError("File is not a valid workup: no job record found.")
        return dict(row)


def get_activity_log(path: str | Path) -> list[dict]:
    """Return all activity log entries for the job, oldest first."""
    path = Path(path)
    with db_connection(path) as conn:
        rows = conn.execute(
            "SELECT * FROM activity_log ORDER BY performed_at ASC"
        ).fetchall()
        return [dict(r) for r in rows]


def _utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
