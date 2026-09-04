"""
Full binder schema. Applied once on .atbw creation.
All monetary amounts use sign convention: DR = positive, CR = negative.
"""

from atbworkup.constants import SCHEMA_VERSION, APP_VERSION  # noqa: F401 (re-exported)

# Each statement is separated so they can be executed individually.
# executescript() is used for initial creation; migrations use individual stmts.
SCHEMA_STATEMENTS = [
    "PRAGMA journal_mode=WAL",
    """
    CREATE TABLE IF NOT EXISTS job (
        job_id            TEXT PRIMARY KEY,
        client_name       TEXT NOT NULL,
        entity_name       TEXT NOT NULL,
        tax_year          INTEGER NOT NULL,
        entity_type       TEXT NOT NULL,
        prepared_by       TEXT NOT NULL,
        reviewer          TEXT,
        workpaper_folder  TEXT,
        accounting_system TEXT,
        is_rollforward    INTEGER NOT NULL DEFAULT 0,
        prior_year_job_id TEXT,
        status            TEXT NOT NULL DEFAULT 'Preparation in Progress',
        workflow_version  INTEGER NOT NULL DEFAULT 1,
        schema_version    TEXT NOT NULL,
        app_version       TEXT NOT NULL,
        created_at        TEXT NOT NULL,
        updated_at        TEXT NOT NULL,
        finalized_at      TEXT,
        finalized_by      TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS accounts (
        account_id     TEXT PRIMARY KEY,
        job_id         TEXT NOT NULL REFERENCES job(job_id),
        account_number TEXT,
        account_name   TEXT NOT NULL,
        account_type   TEXT NOT NULL,
        pbc_balance    REAL NOT NULL DEFAULT 0,
        normal_balance TEXT NOT NULL DEFAULT 'Debit',
        source_row     INTEGER,
        is_mapped      INTEGER NOT NULL DEFAULT 0,
        flag           TEXT,
        sort_order     INTEGER,
        created_at     TEXT NOT NULL,
        updated_at     TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tax_lines (
        tax_line_id         TEXT PRIMARY KEY,
        entity_type         TEXT NOT NULL,
        financial_statement TEXT NOT NULL,
        section             TEXT NOT NULL DEFAULT '',
        section_sort_order  INTEGER NOT NULL DEFAULT 0,
        line_code           TEXT NOT NULL,
        line_name           TEXT NOT NULL,
        sort_order          INTEGER NOT NULL,
        is_active           INTEGER NOT NULL DEFAULT 1,
        tax_year            INTEGER,
        category            TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS mappings (
        mapping_id TEXT PRIMARY KEY,
        account_id TEXT NOT NULL REFERENCES accounts(account_id),
        job_id     TEXT NOT NULL REFERENCES job(job_id),
        tax_line_id TEXT,
        section_id  TEXT,
        mapped_by   TEXT NOT NULL DEFAULT 'preparer',
        mapped_at   TEXT NOT NULL,
        notes       TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sections (
        section_id   TEXT PRIMARY KEY,
        job_id       TEXT NOT NULL REFERENCES job(job_id),
        section_name TEXT NOT NULL,
        entity_type  TEXT NOT NULL,
        sort_order   INTEGER NOT NULL,
        status       TEXT NOT NULL DEFAULT 'Open',
        created_at   TEXT NOT NULL,
        updated_at   TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS journal_entries (
        aje_id          TEXT PRIMARY KEY,
        job_id          TEXT NOT NULL REFERENCES job(job_id),
        entry_type      TEXT NOT NULL,
        entry_number    TEXT NOT NULL,
        description     TEXT NOT NULL,
        originated_by   TEXT NOT NULL DEFAULT 'preparer',
        originated_at   TEXT NOT NULL,
        is_balanced              INTEGER NOT NULL DEFAULT 0,
        status                   TEXT NOT NULL DEFAULT 'Open',
        package_version          INTEGER,
        reviewer_signoff_by      TEXT,
        reviewer_signoff_at      TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS journal_entry_lines (
        line_id    TEXT PRIMARY KEY,
        aje_id     TEXT NOT NULL REFERENCES journal_entries(aje_id),
        account_id TEXT NOT NULL REFERENCES accounts(account_id),
        amount     REAL NOT NULL,
        memo       TEXT,
        sort_order INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS notes (
        note_id         TEXT PRIMARY KEY,
        job_id          TEXT NOT NULL REFERENCES job(job_id),
        note_type       TEXT NOT NULL,
        linked_to_type  TEXT,
        linked_to_id    TEXT,
        body            TEXT NOT NULL,
        created_by      TEXT NOT NULL,
        created_at      TEXT NOT NULL,
        status          TEXT NOT NULL DEFAULT 'Open',
        cleared_by      TEXT,
        cleared_at      TEXT,
        resolved_by     TEXT,
        resolved_at     TEXT,
        package_version INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS signoffs (
        signoff_id      TEXT PRIMARY KEY,
        job_id          TEXT NOT NULL REFERENCES job(job_id),
        signoff_type    TEXT NOT NULL,
        signed_by       TEXT NOT NULL,
        signed_at       TEXT NOT NULL,
        package_version INTEGER,
        notes           TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS packages (
        package_id      TEXT PRIMARY KEY,
        job_id          TEXT NOT NULL REFERENCES job(job_id),
        version_number  INTEGER NOT NULL,
        package_type    TEXT NOT NULL,
        status_label    TEXT NOT NULL,
        file_name       TEXT NOT NULL,
        file_path       TEXT,
        exported_by     TEXT NOT NULL,
        exported_at     TEXT NOT NULL,
        imported_at     TEXT,
        imported_by     TEXT,
        prior_package_id TEXT,
        checksum        TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS activity_log (
        activity_id     TEXT PRIMARY KEY,
        job_id          TEXT NOT NULL REFERENCES job(job_id),
        event_type      TEXT NOT NULL,
        entity_type     TEXT,
        entity_id       TEXT,
        description     TEXT NOT NULL,
        performed_by    TEXT NOT NULL,
        performed_at    TEXT NOT NULL,
        package_version INTEGER,
        metadata_json   TEXT,
        prev_hash       TEXT,
        row_hash        TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS account_groups (
        group_id   TEXT PRIMARY KEY,
        job_id     TEXT NOT NULL REFERENCES job(job_id),
        name       TEXT NOT NULL,
        parent_id  TEXT REFERENCES account_groups(group_id),
        sort_order INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS account_group_members (
        group_id   TEXT NOT NULL REFERENCES account_groups(group_id),
        account_id TEXT NOT NULL REFERENCES accounts(account_id),
        PRIMARY KEY (group_id, account_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS prior_year_balances (
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
    """,
    """
    CREATE TABLE IF NOT EXISTS workpaper_lines (
        wp_line_id   TEXT PRIMARY KEY,
        job_id       TEXT NOT NULL REFERENCES job(job_id),
        workpaper    TEXT NOT NULL,
        description  TEXT NOT NULL,
        amount       REAL NOT NULL DEFAULT 0,
        line_type    TEXT,
        sort_order   INTEGER NOT NULL DEFAULT 0,
        created_at   TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS owners (
        owner_id      TEXT PRIMARY KEY,
        job_id        TEXT NOT NULL REFERENCES job(job_id),
        name          TEXT NOT NULL,
        tin           TEXT,
        ownership_pct REAL NOT NULL DEFAULT 0,
        sort_order    INTEGER NOT NULL DEFAULT 0,
        created_at    TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS consolidation_members (
        member_id    TEXT PRIMARY KEY,
        job_id       TEXT NOT NULL REFERENCES job(job_id),
        member_name  TEXT NOT NULL,
        member_code  TEXT NOT NULL DEFAULT '',
        file_path    TEXT NOT NULL,
        member_type  TEXT NOT NULL DEFAULT 'subsidiary',
        sort_order   INTEGER NOT NULL DEFAULT 0,
        created_at   TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS consolidation_entries (
        entry_id      TEXT PRIMARY KEY,
        job_id        TEXT NOT NULL REFERENCES job(job_id),
        workpaper     TEXT NOT NULL,
        entry_number  TEXT NOT NULL,
        description   TEXT NOT NULL DEFAULT '',
        originated_by TEXT,
        originated_at TEXT NOT NULL,
        status        TEXT NOT NULL DEFAULT 'Open'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS consolidation_entry_lines (
        line_id    TEXT PRIMARY KEY,
        entry_id   TEXT NOT NULL REFERENCES consolidation_entries(entry_id),
        member_id  TEXT NOT NULL REFERENCES consolidation_members(member_id),
        account_id TEXT NOT NULL,
        amount     REAL NOT NULL DEFAULT 0,
        memo       TEXT,
        sort_order INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS consolidation_account_groups (
        group_id   TEXT PRIMARY KEY,
        job_id     TEXT NOT NULL REFERENCES job(job_id),
        name       TEXT NOT NULL,
        parent_id  TEXT REFERENCES consolidation_account_groups(group_id),
        sort_order INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS consolidation_group_members (
        group_id   TEXT NOT NULL REFERENCES consolidation_account_groups(group_id),
        member_id  TEXT NOT NULL REFERENCES consolidation_members(member_id),
        account_id TEXT NOT NULL,
        PRIMARY KEY (group_id, member_id, account_id)
    )
    """,
]

EXPECTED_TABLES = {
    "job", "accounts", "tax_lines", "mappings", "sections",
    "journal_entries", "journal_entry_lines", "notes", "signoffs",
    "packages", "activity_log", "prior_year_balances",
    "account_groups", "account_group_members",
    "workpaper_lines", "owners", "consolidation_members",
    "consolidation_entries", "consolidation_entry_lines",
    "consolidation_account_groups", "consolidation_group_members",
}


def apply_schema(conn) -> None:
    """Apply full schema to an open connection. Safe to call on existing DB (IF NOT EXISTS)."""
    conn.execute("PRAGMA foreign_keys = ON")
    for stmt in SCHEMA_STATEMENTS:
        conn.execute(stmt)
    conn.commit()
