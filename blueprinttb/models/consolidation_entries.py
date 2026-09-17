"""
Account-level consolidation entry CRUD (eliminating entries and consolidated
tax entries, workpaper='elim'/'cte').

Unlike a regular journal entry, each line targets an account that lives in a
*subsidiary's own file* — so a line carries both member_id and account_id.

Sign convention: DR = positive, CR = negative (single signed amount field).
A balanced entry has SUM(amount) == 0.
"""
from __future__ import annotations

import datetime
import uuid


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def next_entry_number(conn, job_id: str, workpaper: str) -> str:
    """Return the next auto-incremented entry number, e.g. EJE-003 / CTE-003."""
    row = conn.execute(
        """SELECT COUNT(*) FROM consolidation_entries
           WHERE job_id = ? AND workpaper = ?""",
        (job_id, workpaper),
    ).fetchone()
    n = row[0] + 1
    prefix = "EJE" if workpaper == "elim" else "CTE"
    return f"{prefix}-{n:03d}"


# ---------------------------------------------------------------------------
# Entries
# ---------------------------------------------------------------------------

def create_entry(conn, *, job_id: str, workpaper: str, description: str,
                 originated_by: str, status: str = "Open") -> dict:
    entry_id = uuid.uuid4().hex
    number = next_entry_number(conn, job_id, workpaper)
    now = _now()
    conn.execute(
        """INSERT INTO consolidation_entries
               (entry_id, job_id, workpaper, entry_number, description,
                originated_by, originated_at, status)
           VALUES (?,?,?,?,?,?,?,?)""",
        (entry_id, job_id, workpaper, number, description, originated_by, now, status),
    )
    return get_entry(conn, entry_id)


def get_entry(conn, entry_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM consolidation_entries WHERE entry_id = ?", (entry_id,)
    ).fetchone()
    return dict(row) if row else None


def get_entries(conn, job_id: str, workpaper: str) -> list[dict]:
    rows = conn.execute(
        """SELECT * FROM consolidation_entries
           WHERE job_id = ? AND workpaper = ?
           ORDER BY entry_number""",
        (job_id, workpaper),
    ).fetchall()
    return [dict(r) for r in rows]


def update_entry(conn, entry_id: str, *, description: str) -> None:
    conn.execute(
        "UPDATE consolidation_entries SET description = ? WHERE entry_id = ?",
        (description, entry_id),
    )


def delete_entry(conn, entry_id: str) -> None:
    conn.execute("DELETE FROM consolidation_entry_lines WHERE entry_id = ?", (entry_id,))
    conn.execute("DELETE FROM consolidation_entries WHERE entry_id = ?", (entry_id,))


# ---------------------------------------------------------------------------
# Lines
# ---------------------------------------------------------------------------

def get_lines(conn, entry_id: str) -> list[dict]:
    rows = conn.execute(
        """SELECT * FROM consolidation_entry_lines
           WHERE entry_id = ?
           ORDER BY sort_order""",
        (entry_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def save_lines(conn, entry_id: str, lines: list[dict]) -> None:
    """
    Replace all lines for an entry with the provided list.
    Each dict: {member_id, account_id, amount, memo}.
    """
    conn.execute("DELETE FROM consolidation_entry_lines WHERE entry_id = ?", (entry_id,))
    for i, line in enumerate(lines):
        conn.execute(
            """INSERT INTO consolidation_entry_lines
                   (line_id, entry_id, member_id, account_id, amount, memo, sort_order)
               VALUES (?,?,?,?,?,?,?)""",
            (
                uuid.uuid4().hex, entry_id,
                line["member_id"], line["account_id"],
                line["amount"], line.get("memo", ""), i,
            ),
        )


def entry_balance(lines: list[dict]) -> float:
    """Sum of amounts for a list of line dicts (in-memory, no DB needed)."""
    return round(sum(ln["amount"] for ln in lines), 2)


def get_all_lines_for_job(conn, job_id: str, workpaper: str) -> list[dict]:
    """
    All lines across all entries of this workpaper type for a job, joined
    with the owning entry's status — used by the combined BS/PL math to
    fold account-level eliminations/CTEs into section totals.
    """
    rows = conn.execute(
        """SELECT cel.*, ce.status, ce.entry_number, ce.description AS entry_description
           FROM consolidation_entry_lines cel
           JOIN consolidation_entries ce ON ce.entry_id = cel.entry_id
           WHERE ce.job_id = ? AND ce.workpaper = ?""",
        (job_id, workpaper),
    ).fetchall()
    return [dict(r) for r in rows]
