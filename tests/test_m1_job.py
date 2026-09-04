"""M1 tests: .atbw creation, schema, metadata, activity log, naming."""
import sqlite3
from pathlib import Path

import pytest

from atbworkup.constants import APP_VERSION, SCHEMA_VERSION
from atbworkup.db.connection import db_connection
from atbworkup.db.schema import EXPECTED_TABLES
from atbworkup.models.job import create_workup, open_workup, get_job, get_activity_log
from atbworkup.utils.naming import suggested_filename


# ---------------------------------------------------------------------------
# File creation
# ---------------------------------------------------------------------------

def test_create_atbw_file_exists(tmp_path, meta):
    path = tmp_path / "test.atbw"
    create_workup(path, meta)
    assert path.exists()


def test_atbw_is_sqlite(tmp_path, meta):
    path = tmp_path / "test.atbw"
    create_workup(path, meta)
    header = path.read_bytes()[:16]
    assert header == b"SQLite format 3\x00"


def test_all_tables_created(atbw_path):
    with db_connection(atbw_path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        tables = {r["name"] for r in rows}
    assert EXPECTED_TABLES.issubset(tables)


def test_job_table_has_one_row(atbw_path):
    with db_connection(atbw_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM job").fetchone()[0]
    assert count == 1


# ---------------------------------------------------------------------------
# Metadata round-trip
# ---------------------------------------------------------------------------

def test_job_metadata_roundtrip(atbw_path, meta):
    job = get_job(atbw_path)
    assert job["client_name"] == meta["client_name"]
    assert job["entity_name"] == meta["entity_name"]
    assert job["tax_year"] == meta["tax_year"]
    assert job["entity_type"] == meta["entity_type"]
    assert job["prepared_by"] == meta["prepared_by"]
    assert job["reviewer"] == meta["reviewer"]
    assert job["accounting_system"] == meta["accounting_system"]


def test_schema_version_set(atbw_path):
    job = get_job(atbw_path)
    assert job["schema_version"] == SCHEMA_VERSION


def test_app_version_set(atbw_path):
    job = get_job(atbw_path)
    assert job["app_version"] == APP_VERSION


def test_status_defaults_to_preparation_in_progress(atbw_path):
    job = get_job(atbw_path)
    assert job["status"] == "Preparation in Progress"


def test_created_at_is_set(atbw_path):
    job = get_job(atbw_path)
    assert job["created_at"]
    # Must look like an ISO-8601 UTC string
    assert "T" in job["created_at"]
    assert job["created_at"].endswith("Z")


# ---------------------------------------------------------------------------
# Activity log
# ---------------------------------------------------------------------------

def test_activity_log_on_create(atbw_path, meta):
    log = get_activity_log(atbw_path)
    events = [e["event_type"] for e in log]
    assert "created_workup" in events


def test_activity_log_create_performed_by(atbw_path, meta):
    log = get_activity_log(atbw_path)
    entry = next(e for e in log if e["event_type"] == "created_workup")
    assert entry["performed_by"] == meta["prepared_by"]


def test_activity_log_on_open(atbw_path):
    open_workup(atbw_path, performed_by="Other User")
    log = get_activity_log(atbw_path)
    open_events = [e for e in log if e["event_type"] == "opened_workup"]
    assert len(open_events) == 1
    assert open_events[0]["performed_by"] == "Other User"


def test_activity_log_open_does_not_duplicate_create(atbw_path):
    open_workup(atbw_path, performed_by="Someone")
    log = get_activity_log(atbw_path)
    create_events = [e for e in log if e["event_type"] == "created_workup"]
    assert len(create_events) == 1


# ---------------------------------------------------------------------------
# File naming
# ---------------------------------------------------------------------------

def test_suggested_filename():
    name = suggested_filename(2025, "ABC Company")
    assert name == "2025 ABC Company Prep in Progress V01.atbr.xlsx"


def test_suggested_filename_strips_whitespace():
    name = suggested_filename(2025, "  ABC  ")
    assert name.startswith("2025 ABC")


def test_suggested_filename_sanitizes_slash():
    name = suggested_filename(2025, "A/B Corp")
    assert "/" not in name


# ---------------------------------------------------------------------------
# Foreign key enforcement
# ---------------------------------------------------------------------------

def test_foreign_keys_enforced(atbw_path):
    with pytest.raises(sqlite3.IntegrityError):
        with db_connection(atbw_path) as conn:
            import datetime, uuid
            now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            conn.execute(
                """
                INSERT INTO accounts
                    (account_id, job_id, account_name, account_type, normal_balance, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (uuid.uuid4().hex, "nonexistent-job-id", "Test", "Asset", "Debit", now, now),
            )


# ---------------------------------------------------------------------------
# Open non-existent file
# ---------------------------------------------------------------------------

def test_open_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        open_workup(tmp_path / "no_such_file.atbw", performed_by="x")


def test_open_invalid_sqlite_raises(tmp_path):
    bad = tmp_path / "bad.atbw"
    bad.write_bytes(b"this is not sqlite")
    with pytest.raises(Exception):
        open_workup(bad, performed_by="x")
