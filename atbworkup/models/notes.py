"""
Notes model — preparer notes linked to accounts or journal entries.
"""
from __future__ import annotations

import datetime
import uuid


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def create_note(conn, *, job_id: str, body: str, created_by: str,
                linked_to_type: str | None = None,
                linked_to_id: str | None = None,
                note_type: str = "preparer") -> dict:
    note_id = uuid.uuid4().hex
    now = _now()
    conn.execute(
        """INSERT INTO notes
               (note_id, job_id, note_type, linked_to_type, linked_to_id,
                body, created_by, created_at, status)
           VALUES (?,?,?,?,?,?,?,?,'Open')""",
        (note_id, job_id, note_type, linked_to_type, linked_to_id,
         body, created_by, now),
    )
    return get_note(conn, note_id)


def get_note(conn, note_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM notes WHERE note_id = ?", (note_id,)
    ).fetchone()
    return dict(row) if row else None


def get_notes(conn, job_id: str, status_filter: str = "Open") -> list[dict]:
    """
    Return notes for a job.
    status_filter: 'Open' | 'All'
    Joins accounts/journal_entries to get display names for linked entities.
    """
    where = "n.job_id = ?"
    params: list = [job_id]
    if status_filter == "Open":
        where += " AND n.status = 'Open'"

    rows = conn.execute(
        f"""
        SELECT
            n.*,
            CASE
                WHEN n.linked_to_type = 'account'
                     THEN COALESCE(a.account_number || '  ' || a.account_name,
                                   a.account_name)
                WHEN n.linked_to_type = 'journal_entry'
                     THEN je.entry_number || ' — ' || je.description
                ELSE NULL
            END AS linked_display
        FROM notes n
        LEFT JOIN accounts       a  ON a.account_id  = n.linked_to_id
                                    AND n.linked_to_type = 'account'
        LEFT JOIN journal_entries je ON je.aje_id     = n.linked_to_id
                                    AND n.linked_to_type = 'journal_entry'
        WHERE {where}
        ORDER BY n.created_at DESC
        """,
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def clear_note(conn, note_id: str, cleared_by: str) -> None:
    now = _now()
    conn.execute(
        """UPDATE notes
           SET status = 'Cleared', cleared_by = ?, cleared_at = ?
           WHERE note_id = ?""",
        (cleared_by, now, note_id),
    )


def resolve_note(conn, note_id: str, resolved_by: str) -> None:
    now = _now()
    conn.execute(
        """UPDATE notes
           SET status = 'Resolved', resolved_by = ?, resolved_at = ?
           WHERE note_id = ?""",
        (resolved_by, now, note_id),
    )


def open_note_count(conn, job_id: str) -> int:
    """Count open notes that affect finalization diagnostics (excludes delivery notes)."""
    return conn.execute(
        "SELECT COUNT(*) FROM notes "
        "WHERE job_id = ? AND status = 'Open' AND note_type != 'delivery'",
        (job_id,),
    ).fetchone()[0]


def open_delivery_note_count(conn, job_id: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM notes "
        "WHERE job_id = ? AND status = 'Open' AND note_type = 'delivery'",
        (job_id,),
    ).fetchone()[0]


def reviewer_note_account_ids(conn, job_id: str) -> set:
    """Return the set of account_ids with at least one open reviewer note."""
    rows = conn.execute(
        "SELECT linked_to_id FROM notes "
        "WHERE job_id = ? AND note_type = 'reviewer' AND status = 'Open' "
        "AND linked_to_type = 'account'",
        (job_id,),
    ).fetchall()
    return {r[0] for r in rows}
