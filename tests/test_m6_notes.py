"""M6 tests: note creation, filtering, clearing, open count."""
import pytest
import uuid
import datetime

from atbworkup.db.connection import db_connection
from atbworkup.models.notes import create_note, get_notes, clear_note, open_note_count
from atbworkup.models.job import get_job


def _insert_account(conn, job_id, *, name="Cash"):
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    aid = uuid.uuid4().hex
    conn.execute(
        """INSERT INTO accounts
               (account_id, job_id, account_number, account_name, account_type,
                pbc_balance, normal_balance, sort_order, is_mapped, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,0,?,?)""",
        (aid, job_id, "1000", name, "Asset", 0.0, "Debit", 0, now, now),
    )
    return aid


# ---------------------------------------------------------------------------

def test_create_note_linked_to_account(atbw_path):
    job = get_job(atbw_path)
    with db_connection(atbw_path) as conn:
        aid = _insert_account(conn, job["job_id"])
        note = create_note(conn, job_id=job["job_id"], body="Check this balance",
                           created_by="preparer", linked_to_type="account",
                           linked_to_id=aid)
    assert note["note_id"]
    assert note["status"] == "Open"
    assert note["body"] == "Check this balance"
    assert note["linked_to_type"] == "account"


def test_get_notes_open_filter(atbw_path):
    job = get_job(atbw_path)
    with db_connection(atbw_path) as conn:
        aid = _insert_account(conn, job["job_id"], name="AR")
        create_note(conn, job_id=job["job_id"], body="Open note",
                    created_by="preparer", linked_to_type="account", linked_to_id=aid)
        n2 = create_note(conn, job_id=job["job_id"], body="Will clear",
                         created_by="preparer", linked_to_type="account", linked_to_id=aid)
        clear_note(conn, n2["note_id"], "preparer")

    with db_connection(atbw_path) as conn:
        open_notes = get_notes(conn, job["job_id"], "Open")
        all_notes  = get_notes(conn, job["job_id"], "All")

    assert len(open_notes) == 1
    assert open_notes[0]["body"] == "Open note"
    assert len(all_notes) == 2


def test_clear_note(atbw_path):
    job = get_job(atbw_path)
    with db_connection(atbw_path) as conn:
        note = create_note(conn, job_id=job["job_id"], body="To clear",
                           created_by="preparer")
        clear_note(conn, note["note_id"], "preparer")

    with db_connection(atbw_path) as conn:
        notes = get_notes(conn, job["job_id"], "All")
    cleared = next(n for n in notes if n["note_id"] == note["note_id"])
    assert cleared["status"] == "Cleared"
    assert cleared["cleared_by"] == "preparer"
    assert cleared["cleared_at"] is not None


def test_open_note_count(atbw_path):
    job = get_job(atbw_path)
    with db_connection(atbw_path) as conn:
        assert open_note_count(conn, job["job_id"]) == 0
        n1 = create_note(conn, job_id=job["job_id"], body="A", created_by="preparer")
        n2 = create_note(conn, job_id=job["job_id"], body="B", created_by="preparer")
        assert open_note_count(conn, job["job_id"]) == 2
        clear_note(conn, n1["note_id"], "preparer")
        assert open_note_count(conn, job["job_id"]) == 1


def test_note_linked_display_includes_account_name(atbw_path):
    job = get_job(atbw_path)
    with db_connection(atbw_path) as conn:
        aid = _insert_account(conn, job["job_id"], name="Checking")
        create_note(conn, job_id=job["job_id"], body="Verify",
                    created_by="preparer", linked_to_type="account", linked_to_id=aid)

    with db_connection(atbw_path) as conn:
        notes = get_notes(conn, job["job_id"], "Open")
    assert "Checking" in notes[0]["linked_display"]


def test_note_not_linked(atbw_path):
    job = get_job(atbw_path)
    with db_connection(atbw_path) as conn:
        note = create_note(conn, job_id=job["job_id"], body="General note",
                           created_by="preparer")
    assert note["linked_to_type"] is None
    assert note["linked_to_id"] is None
