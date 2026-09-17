"""
Tax Grouping tie-out flags — a preparer's "I entered this into the return
and it ties out" mark on the Tax Grouping report tab, deliberately
independent of the Trial Balance's own account.flag (see
accounts.set_flag): tying out against the return is a different fact than
the trial-balance-level question/reviewed/issue flag, and sharing one
column would mean setting one silently changes what the other means.

Auto-invalidation: when a preparer marks a line "reviewed" (tied out), the
then-current statement value (FTAX for P&L lines, FINAL for Balance Sheet
lines — decided by the caller) is snapshotted as `tied_value`. Every time
the report is rebuilt, invalidate_stale_ties() compares that snapshot
against the freshly computed live value; if the trial balance moved since
the tie-out, the flag is downgraded back to "question" so the preparer
sees it needs re-verifying instead of silently trusting a stale tie-out.

Deliberately just two click-reachable states (blank / checked), not the
Trial Balance flag's four-state cycle: clicking always means "toggle
tied-out," and "question" is never something a click produces -- it only
ever appears automatically, via invalidate_stale_ties() above, when the
trial balance moves after a tie-out.
"""
from __future__ import annotations

import datetime

FLAG_REVIEWED = "reviewed"
FLAG_STALE    = "question"   # set only by invalidate_stale_ties(), never by a click


def _utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_ties(conn, job_id: str) -> dict[str, dict]:
    """{account_id: {flag, tied_value, tied_by, tied_at}} for this job."""
    rows = conn.execute(
        "SELECT account_id, flag, tied_value, tied_by, tied_at "
        "FROM tax_grouping_ties WHERE job_id = ?",
        (job_id,),
    ).fetchall()
    return {r["account_id"]: dict(r) for r in rows}


def cycle_tie_flag(conn, job_id: str, account_id: str, current_value: float | None,
                   tied_by: str) -> str | None:
    """
    Toggle this account's tie-out mark: anything other than "reviewed"
    (blank, or "question" from a stale tie-out) becomes "reviewed" and
    snapshots `current_value` as the asserted tied-out number; "reviewed"
    itself clears back to blank. Returns the new flag.
    """
    row = conn.execute(
        "SELECT flag FROM tax_grouping_ties WHERE account_id = ?", (account_id,)
    ).fetchone()
    current = row["flag"] if row else None
    next_flag = None if current == FLAG_REVIEWED else FLAG_REVIEWED

    conn.execute("DELETE FROM tax_grouping_ties WHERE account_id = ?", (account_id,))
    if next_flag is not None:
        tied_value = round(current_value, 2) if current_value is not None else None
        conn.execute(
            """INSERT INTO tax_grouping_ties
                   (account_id, job_id, flag, tied_value, tied_by, tied_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (account_id, job_id, next_flag, tied_value, tied_by, _utcnow()),
        )
    return next_flag


def invalidate_stale_ties(conn, job_id: str, current_values: dict[str, float]) -> set[str]:
    """
    For every account currently flagged "reviewed" (tied out), compare its
    snapshotted value to `current_values` (freshly computed from the live
    trial balance -- FTAX for P&L lines, FINAL for Balance Sheet lines).
    Any mismatch -- including an account that no longer appears at all,
    e.g. unmapped or deleted -- means the trial balance moved since the
    tie-out, so the flag is downgraded back to "question", NOT cleared to
    None, so it still visibly demands attention rather than silently
    reverting to a blank cell. Returns the set of account_ids downgraded.
    """
    rows = conn.execute(
        "SELECT account_id, tied_value FROM tax_grouping_ties "
        "WHERE job_id = ? AND flag = 'reviewed'",
        (job_id,),
    ).fetchall()
    stale: set[str] = set()
    for row in rows:
        live = current_values.get(row["account_id"])
        tied = row["tied_value"]
        if live is None or tied is None or abs(live - tied) > 0.005:
            stale.add(row["account_id"])
    if stale:
        conn.executemany(
            "UPDATE tax_grouping_ties SET flag = 'question' WHERE account_id = ?",
            [(aid,) for aid in stale],
        )
    return stale
