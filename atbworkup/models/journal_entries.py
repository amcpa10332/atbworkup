"""
Journal entry CRUD.

Sign convention: DR = positive, CR = negative (single signed amount field).
A balanced entry has SUM(amount) == 0.
"""
from __future__ import annotations

import datetime
import uuid


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def next_entry_number(conn, job_id: str, entry_type: str) -> str:
    """Return the next auto-incremented entry number, e.g. AJE-003."""
    row = conn.execute(
        """SELECT COUNT(*) FROM journal_entries
           WHERE job_id = ? AND entry_type = ?""",
        (job_id, entry_type),
    ).fetchone()
    n = row[0] + 1
    return f"{entry_type}-{n:03d}"


# ---------------------------------------------------------------------------
# Journal entries
# ---------------------------------------------------------------------------

def create_entry(conn, *, job_id: str, entry_type: str, description: str,
                 originated_by: str, status: str = "Shell") -> dict:
    """Create a new (empty) journal entry and return it as a dict."""
    aje_id = uuid.uuid4().hex
    number = next_entry_number(conn, job_id, entry_type)
    now = _now()
    conn.execute(
        """INSERT INTO journal_entries
               (aje_id, job_id, entry_type, entry_number, description,
                originated_by, originated_at, is_balanced, status)
           VALUES (?,?,?,?,?,?,?,0,?)""",
        (aje_id, job_id, entry_type, number, description, originated_by, now, status),
    )
    return get_entry(conn, aje_id)


def get_entry(conn, aje_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM journal_entries WHERE aje_id = ?", (aje_id,)
    ).fetchone()
    return dict(row) if row else None


def get_entries(conn, job_id: str) -> list[dict]:
    """All entries for a job, ordered by type then number."""
    rows = conn.execute(
        """SELECT * FROM journal_entries
           WHERE job_id = ?
           ORDER BY entry_type, entry_number""",
        (job_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def signoff_entry(conn, aje_id: str, signed_by: str) -> None:
    """Record a reviewer sign-off on a journal entry."""
    conn.execute(
        "UPDATE journal_entries SET reviewer_signoff_by=?, reviewer_signoff_at=? WHERE aje_id=?",
        (signed_by, _now(), aje_id),
    )


def remove_signoff(conn, aje_id: str) -> None:
    """Clear the reviewer sign-off from a journal entry."""
    conn.execute(
        "UPDATE journal_entries SET reviewer_signoff_by=NULL, reviewer_signoff_at=NULL WHERE aje_id=?",
        (aje_id,),
    )


def update_entry(conn, aje_id: str, *, description: str) -> None:
    conn.execute(
        "UPDATE journal_entries SET description = ? WHERE aje_id = ?",
        (description, aje_id),
    )


def delete_entry(conn, aje_id: str) -> None:
    """Delete an entry and all its lines (FK cascade not guaranteed; explicit delete)."""
    conn.execute("DELETE FROM journal_entry_lines WHERE aje_id = ?", (aje_id,))
    conn.execute("DELETE FROM journal_entries WHERE aje_id = ?", (aje_id,))


# ---------------------------------------------------------------------------
# Lines
# ---------------------------------------------------------------------------

def get_lines(conn, aje_id: str) -> list[dict]:
    rows = conn.execute(
        """SELECT jel.*, a.account_number, a.account_name
           FROM journal_entry_lines jel
           JOIN accounts a ON a.account_id = jel.account_id
           WHERE jel.aje_id = ?
           ORDER BY jel.sort_order""",
        (aje_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def upsert_line(conn, *, aje_id: str, account_id: str, amount: float,
                memo: str = "", sort_order: int = 0,
                line_id: str | None = None) -> str:
    """Insert or replace a line. Returns line_id."""
    if line_id:
        conn.execute(
            """UPDATE journal_entry_lines
               SET account_id=?, amount=?, memo=?, sort_order=?
               WHERE line_id=?""",
            (account_id, amount, memo, sort_order, line_id),
        )
        return line_id
    lid = uuid.uuid4().hex
    conn.execute(
        """INSERT INTO journal_entry_lines
               (line_id, aje_id, account_id, amount, memo, sort_order)
           VALUES (?,?,?,?,?,?)""",
        (lid, aje_id, account_id, amount, memo, sort_order),
    )
    return lid


def delete_line(conn, line_id: str) -> None:
    conn.execute("DELETE FROM journal_entry_lines WHERE line_id = ?", (line_id,))


def save_lines(conn, aje_id: str, lines: list[dict]) -> None:
    """
    Replace all lines for an entry with the provided list.
    Each dict: {account_id, amount, memo}.
    Recalculates is_balanced.
    """
    conn.execute("DELETE FROM journal_entry_lines WHERE aje_id = ?", (aje_id,))
    for i, line in enumerate(lines):
        upsert_line(
            conn,
            aje_id=aje_id,
            account_id=line["account_id"],
            amount=line["amount"],
            memo=line.get("memo", ""),
            sort_order=i,
        )
    _refresh_balance_flag(conn, aje_id)


def _refresh_balance_flag(conn, aje_id: str) -> None:
    row = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM journal_entry_lines WHERE aje_id = ?",
        (aje_id,),
    ).fetchone()
    total = round(row[0], 2)
    is_balanced = 1 if abs(total) < 0.005 else 0
    status = "Open" if is_balanced else "Shell"
    conn.execute(
        "UPDATE journal_entries SET is_balanced=?, status=? WHERE aje_id=?",
        (is_balanced, status, aje_id),
    )


def entry_balance(lines: list[dict]) -> float:
    """Sum of amounts for a list of line dicts (in-memory, no DB needed)."""
    return round(sum(ln["amount"] for ln in lines), 2)
