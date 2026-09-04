"""
Account regrouping for consolidated binders — lets a preparer group accounts
across subsidiaries for display in the combined statements, independent of
each subsidiary's own account_groups (which only apply within that sub's
own workpaper).

A group member is identified by (member_id, account_id) since the same
account_id can exist in more than one subsidiary's file.
"""
from __future__ import annotations

import datetime
import uuid


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def create_group(conn, *, job_id: str, name: str, parent_id: str | None = None,
                 sort_order: int = 0) -> str:
    group_id = uuid.uuid4().hex
    conn.execute(
        """INSERT INTO consolidation_account_groups
               (group_id, job_id, name, parent_id, sort_order, created_at)
           VALUES (?,?,?,?,?,?)""",
        (group_id, job_id, name, parent_id, sort_order, _now()),
    )
    return group_id


def rename_group(conn, group_id: str, name: str) -> None:
    conn.execute(
        "UPDATE consolidation_account_groups SET name = ? WHERE group_id = ?",
        (name, group_id),
    )


def delete_group(conn, group_id: str) -> None:
    conn.execute("DELETE FROM consolidation_group_members WHERE group_id = ?", (group_id,))
    conn.execute("DELETE FROM consolidation_account_groups WHERE group_id = ?", (group_id,))


def get_groups(conn, job_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM consolidation_account_groups WHERE job_id = ? ORDER BY sort_order, name",
        (job_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def add_member(conn, group_id: str, member_id: str, account_id: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO consolidation_group_members (group_id, member_id, account_id) "
        "VALUES (?,?,?)",
        (group_id, member_id, account_id),
    )


def remove_member(conn, group_id: str, member_id: str, account_id: str) -> None:
    conn.execute(
        "DELETE FROM consolidation_group_members "
        "WHERE group_id = ? AND member_id = ? AND account_id = ?",
        (group_id, member_id, account_id),
    )


def get_group_members(conn, job_id: str) -> dict[tuple[str, str], str]:
    """{(member_id, account_id): group_id} for every grouped account in this job."""
    rows = conn.execute(
        """SELECT gm.group_id, gm.member_id, gm.account_id
           FROM consolidation_group_members gm
           JOIN consolidation_account_groups g ON g.group_id = gm.group_id
           WHERE g.job_id = ?""",
        (job_id,),
    ).fetchall()
    return {(r["member_id"], r["account_id"]): r["group_id"] for r in rows}
