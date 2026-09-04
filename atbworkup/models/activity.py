"""
Append-only activity log. No updates or deletes.

Each row is hash-chained to the one before it for the same job (prev_hash +
this row's fields -> row_hash), tamper-evident-log style. A student editing
or deleting a row directly in the SQLite file (to erase a suspicious event,
or backdate work) changes nothing visible in the UI, but breaks the chain —
detectable via verify_activity_chain() and surfaced in the exported
package's __manifest tab.
"""
from __future__ import annotations

import datetime
import hashlib

from atbworkup.utils.ids import new_uuid

GENESIS_HASH = "0" * 64


def compute_row_hash(prev_hash, job_id, event_type, entity_type, entity_id,
                     description, performed_by, performed_at,
                     package_version, metadata_json) -> str:
    payload = "|".join(
        "" if x is None else str(x)
        for x in (prev_hash, job_id, event_type, entity_type, entity_id,
                  description, performed_by, performed_at, package_version,
                  metadata_json)
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _last_hash(conn, job_id: str) -> str:
    row = conn.execute(
        "SELECT row_hash FROM activity_log WHERE job_id = ? ORDER BY rowid DESC LIMIT 1",
        (job_id,),
    ).fetchone()
    return row[0] if row and row[0] else GENESIS_HASH


def log_activity(
    conn,
    *,
    job_id: str,
    event_type: str,
    description: str,
    performed_by: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    package_version: int | None = None,
    metadata_json: str | None = None,
) -> str:
    activity_id = new_uuid()
    now = _utcnow()
    prev_hash = _last_hash(conn, job_id)
    row_hash = compute_row_hash(
        prev_hash, job_id, event_type, entity_type, entity_id,
        description, performed_by, now, package_version, metadata_json,
    )
    conn.execute(
        """
        INSERT INTO activity_log
            (activity_id, job_id, event_type, entity_type, entity_id,
             description, performed_by, performed_at, package_version, metadata_json,
             prev_hash, row_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (activity_id, job_id, event_type, entity_type, entity_id,
         description, performed_by, now, package_version, metadata_json,
         prev_hash, row_hash),
    )
    return activity_id


def verify_activity_chain(conn, job_id: str) -> tuple[bool, str | None]:
    """
    Recompute the hash chain for job_id's activity_log rows in insertion
    order. Returns (True, None) if every row's stored hash matches its
    recomputed value, else (False, activity_id) of the first row that
    doesn't — i.e. the first sign of tampering or deletion.
    """
    rows = conn.execute(
        """SELECT activity_id, event_type, entity_type, entity_id, description,
                  performed_by, performed_at, package_version, metadata_json,
                  prev_hash, row_hash
           FROM activity_log WHERE job_id = ? ORDER BY rowid""",
        (job_id,),
    ).fetchall()
    expected_prev = GENESIS_HASH
    for r in rows:
        recomputed = compute_row_hash(
            expected_prev, job_id, r["event_type"], r["entity_type"], r["entity_id"],
            r["description"], r["performed_by"], r["performed_at"],
            r["package_version"], r["metadata_json"],
        )
        if r["prev_hash"] != expected_prev or r["row_hash"] != recomputed:
            return False, r["activity_id"]
        expected_prev = r["row_hash"]
    return True, None


def _utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
