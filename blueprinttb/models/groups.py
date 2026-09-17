"""Account grouping model — per-job, independent of tax-line mappings."""
from __future__ import annotations

import datetime
import uuid


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def create_group(conn, job_id: str, name: str, parent_id: str | None = None) -> str:
    """Create a new group and return its group_id."""
    group_id = str(uuid.uuid4())
    row = conn.execute(
        "SELECT COALESCE(MAX(sort_order), 0) FROM account_groups "
        "WHERE job_id = ? AND parent_id IS ?",
        (job_id, parent_id),
    ).fetchone()
    sort_order = (row[0] or 0) + 10
    conn.execute(
        "INSERT INTO account_groups (group_id, job_id, name, parent_id, sort_order, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (group_id, job_id, name, parent_id, sort_order, _now()),
    )
    return group_id


def get_groups(conn, job_id: str) -> list[dict]:
    """Return all groups for the job ordered by sort_order."""
    rows = conn.execute(
        "SELECT group_id, name, parent_id, sort_order FROM account_groups "
        "WHERE job_id = ? ORDER BY sort_order",
        (job_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def add_accounts_to_group(conn, group_id: str, account_ids: list[str]) -> None:
    """Add accounts to a group, silently ignoring duplicates."""
    for aid in account_ids:
        # Remove from any existing group first (one account = one group)
        conn.execute(
            "DELETE FROM account_group_members WHERE account_id = ?", (aid,)
        )
        conn.execute(
            "INSERT OR IGNORE INTO account_group_members (group_id, account_id) VALUES (?, ?)",
            (group_id, aid),
        )


def remove_accounts_from_groups(conn, account_ids: list[str]) -> None:
    """Remove accounts from whatever group they belong to."""
    for aid in account_ids:
        conn.execute(
            "DELETE FROM account_group_members WHERE account_id = ?", (aid,)
        )


def get_group_members(conn, job_id: str) -> dict[str, str]:
    """Return {account_id: group_id} for all grouped accounts in the job."""
    rows = conn.execute(
        "SELECT m.account_id, m.group_id FROM account_group_members m "
        "JOIN account_groups g ON g.group_id = m.group_id "
        "WHERE g.job_id = ?",
        (job_id,),
    ).fetchall()
    return {r["account_id"]: r["group_id"] for r in rows}


def delete_group(conn, group_id: str) -> None:
    """Delete a group. Children are reparented to the deleted group's parent."""
    row = conn.execute(
        "SELECT parent_id FROM account_groups WHERE group_id = ?", (group_id,)
    ).fetchone()
    parent_id = row["parent_id"] if row else None
    conn.execute(
        "UPDATE account_groups SET parent_id = ? WHERE parent_id = ?",
        (parent_id, group_id),
    )
    conn.execute("DELETE FROM account_group_members WHERE group_id = ?", (group_id,))
    conn.execute("DELETE FROM account_groups WHERE group_id = ?", (group_id,))


def rename_group(conn, group_id: str, name: str) -> None:
    conn.execute("UPDATE account_groups SET name = ? WHERE group_id = ?", (name, group_id))
