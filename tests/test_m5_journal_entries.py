"""M5 tests: journal entry creation, balance flag, computed columns."""
import pytest
import uuid
import datetime

from atbworkup.db.connection import db_connection
from atbworkup.models.journal_entries import (
    create_entry, get_entry, get_entries, get_lines,
    save_lines, delete_entry, entry_balance, next_entry_number, update_entry,
)
from atbworkup.models.accounts import get_account_balances
from atbworkup.models.job import get_job


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _insert_account(conn, job_id, *, name, balance=0.0):
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    aid = uuid.uuid4().hex
    conn.execute(
        """INSERT INTO accounts
               (account_id, job_id, account_number, account_name, account_type,
                pbc_balance, normal_balance, sort_order, is_mapped, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,0,?,?)""",
        (aid, job_id, "", name, "Asset", balance, "Debit", 0, now, now),
    )
    return aid


# ---------------------------------------------------------------------------
# Entry numbering
# ---------------------------------------------------------------------------

def test_first_aje_numbered_001(atbw_path):
    job = get_job(atbw_path)
    with db_connection(atbw_path) as conn:
        n = next_entry_number(conn, job["job_id"], "AJE")
    assert n == "AJE-001"


def test_entry_numbers_increment(atbw_path):
    job = get_job(atbw_path)
    with db_connection(atbw_path) as conn:
        create_entry(conn, job_id=job["job_id"], entry_type="AJE",
                     description="First", originated_by="preparer")
        n = next_entry_number(conn, job["job_id"], "AJE")
    assert n == "AJE-002"


def test_rje_numbering_independent_of_aje(atbw_path):
    job = get_job(atbw_path)
    with db_connection(atbw_path) as conn:
        create_entry(conn, job_id=job["job_id"], entry_type="AJE",
                     description="AJE", originated_by="preparer")
        n = next_entry_number(conn, job["job_id"], "RJE")
    assert n == "RJE-001"


# ---------------------------------------------------------------------------
# Entry CRUD
# ---------------------------------------------------------------------------

def test_create_entry_returns_dict(atbw_path):
    job = get_job(atbw_path)
    with db_connection(atbw_path) as conn:
        entry = create_entry(conn, job_id=job["job_id"], entry_type="AJE",
                             description="Test entry", originated_by="preparer")
    assert entry["entry_number"] == "AJE-001"
    assert entry["entry_type"] == "AJE"
    assert entry["is_balanced"] == 0
    assert entry["status"] == "Shell"


def test_get_entries_returns_all(atbw_path):
    job = get_job(atbw_path)
    with db_connection(atbw_path) as conn:
        create_entry(conn, job_id=job["job_id"], entry_type="AJE",
                     description="A", originated_by="preparer")
        create_entry(conn, job_id=job["job_id"], entry_type="RJE",
                     description="B", originated_by="preparer")
    with db_connection(atbw_path) as conn:
        entries = get_entries(conn, job["job_id"])
    assert len(entries) == 2


def test_update_entry_description(atbw_path):
    job = get_job(atbw_path)
    with db_connection(atbw_path) as conn:
        entry = create_entry(conn, job_id=job["job_id"], entry_type="AJE",
                             description="Old", originated_by="preparer")
        update_entry(conn, entry["aje_id"], description="New")
    with db_connection(atbw_path) as conn:
        updated = get_entry(conn, entry["aje_id"])
    assert updated["description"] == "New"


def test_delete_entry_removes_lines(atbw_path):
    job = get_job(atbw_path)
    with db_connection(atbw_path) as conn:
        aid = _insert_account(conn, job["job_id"], name="Cash", balance=1000.0)
        entry = create_entry(conn, job_id=job["job_id"], entry_type="AJE",
                             description="To delete", originated_by="preparer")
        save_lines(conn, entry["aje_id"],
                   [{"account_id": aid, "amount": 100.0, "memo": ""},
                    {"account_id": aid, "amount": -100.0, "memo": ""}])
        delete_entry(conn, entry["aje_id"])
    with db_connection(atbw_path) as conn:
        assert get_entry(conn, entry["aje_id"]) is None
        lines = get_lines(conn, entry["aje_id"])
    assert lines == []


# ---------------------------------------------------------------------------
# Balance flag
# ---------------------------------------------------------------------------

def test_balanced_entry_flagged(atbw_path):
    job = get_job(atbw_path)
    with db_connection(atbw_path) as conn:
        a1 = _insert_account(conn, job["job_id"], name="Cash")
        a2 = _insert_account(conn, job["job_id"], name="Revenue")
        entry = create_entry(conn, job_id=job["job_id"], entry_type="AJE",
                             description="Balanced", originated_by="preparer")
        save_lines(conn, entry["aje_id"],
                   [{"account_id": a1, "amount":  500.0, "memo": ""},
                    {"account_id": a2, "amount": -500.0, "memo": ""}])
    with db_connection(atbw_path) as conn:
        updated = get_entry(conn, entry["aje_id"])
    assert updated["is_balanced"] == 1
    assert updated["status"] == "Open"


def test_unbalanced_entry_not_flagged(atbw_path):
    job = get_job(atbw_path)
    with db_connection(atbw_path) as conn:
        a1 = _insert_account(conn, job["job_id"], name="Cash2")
        entry = create_entry(conn, job_id=job["job_id"], entry_type="AJE",
                             description="Unbalanced", originated_by="preparer")
        save_lines(conn, entry["aje_id"],
                   [{"account_id": a1, "amount": 500.0, "memo": ""}])
    with db_connection(atbw_path) as conn:
        updated = get_entry(conn, entry["aje_id"])
    assert updated["is_balanced"] == 0
    assert updated["status"] == "Shell"


def test_entry_balance_helper():
    lines = [{"amount": 300.0}, {"amount": -300.0}]
    assert entry_balance(lines) == pytest.approx(0.0)

    lines2 = [{"amount": 100.0}, {"amount": 50.0}]
    assert entry_balance(lines2) == pytest.approx(150.0)


# ---------------------------------------------------------------------------
# Computed columns update after JE
# ---------------------------------------------------------------------------

def test_aje_updates_adj_column(atbw_path):
    job = get_job(atbw_path)
    with db_connection(atbw_path) as conn:
        a1 = _insert_account(conn, job["job_id"], name="Cash", balance=1000.0)
        a2 = _insert_account(conn, job["job_id"], name="Revenue", balance=-1000.0)
        entry = create_entry(conn, job_id=job["job_id"], entry_type="AJE",
                             description="Accrual", originated_by="preparer")
        save_lines(conn, entry["aje_id"],
                   [{"account_id": a1, "amount":  200.0, "memo": ""},
                    {"account_id": a2, "amount": -200.0, "memo": ""}])
    with db_connection(atbw_path) as conn:
        accts = {a["account_id"]: a for a in get_account_balances(conn, job["job_id"])}
    assert accts[a1]["adj"]  == pytest.approx(1200.0)
    assert accts[a2]["adj"]  == pytest.approx(-1200.0)


def test_rje_updates_final_not_adj(atbw_path):
    job = get_job(atbw_path)
    with db_connection(atbw_path) as conn:
        a1 = _insert_account(conn, job["job_id"], name="Prepaid", balance=1200.0)
        a2 = _insert_account(conn, job["job_id"], name="Expense", balance=0.0)
        entry = create_entry(conn, job_id=job["job_id"], entry_type="RJE",
                             description="Reverse prepaid", originated_by="preparer")
        save_lines(conn, entry["aje_id"],
                   [{"account_id": a1, "amount": -1200.0, "memo": ""},
                    {"account_id": a2, "amount":  1200.0, "memo": ""}])
    with db_connection(atbw_path) as conn:
        accts = {a["account_id"]: a for a in get_account_balances(conn, job["job_id"])}
    assert accts[a1]["adj"]   == pytest.approx(1200.0)   # RJE doesn't touch adj
    assert accts[a1]["final"] == pytest.approx(0.0)


def test_ftje_updates_ftax_not_final(atbw_path):
    job = get_job(atbw_path)
    with db_connection(atbw_path) as conn:
        a1 = _insert_account(conn, job["job_id"], name="BuildingFT", balance=50000.0)
        a2 = _insert_account(conn, job["job_id"], name="AccumDeprFT", balance=0.0)
        entry = create_entry(conn, job_id=job["job_id"], entry_type="FTJE",
                             description="Tax depreciation", originated_by="preparer")
        save_lines(conn, entry["aje_id"],
                   [{"account_id": a1, "amount":  -5000.0, "memo": ""},
                    {"account_id": a2, "amount":   5000.0, "memo": ""}])
    with db_connection(atbw_path) as conn:
        accts = {a["account_id"]: a for a in get_account_balances(conn, job["job_id"])}
    assert accts[a1]["final"] == pytest.approx(50000.0)   # FTJE doesn't touch final
    assert accts[a1]["ftax"]  == pytest.approx(45000.0)
