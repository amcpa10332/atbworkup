"""M3 tests: financial statement grouping, computed columns, subtotals."""
import pytest
from pathlib import Path

from atbworkup.db.connection import db_connection
from atbworkup.models.accounts import get_account_balances, get_grouped_balances, set_flag
from atbworkup.models.job import get_job


FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _insert_account(conn, job_id, *, name, number="", balance, acct_type="Asset",
                    normal="Debit", sort=0):
    import datetime, uuid
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    aid = uuid.uuid4().hex
    conn.execute(
        """INSERT INTO accounts
               (account_id, job_id, account_number, account_name, account_type,
                pbc_balance, normal_balance, sort_order, is_mapped, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,0,?,?)""",
        (aid, job_id, number, name, acct_type, balance, normal, sort, now, now),
    )
    return aid


def _insert_aje(conn, job_id, account_id, amount, entry_type="AJE"):
    import datetime, uuid
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    aje_id = uuid.uuid4().hex
    conn.execute(
        """INSERT INTO journal_entries
               (aje_id, job_id, entry_type, entry_number, description,
                originated_by, originated_at, is_balanced, status)
           VALUES (?,?,?,?,?, 'preparer',?,0,'Open')""",
        (aje_id, job_id, entry_type, f"{entry_type}-001", "test", now),
    )
    line_id = uuid.uuid4().hex
    conn.execute(
        """INSERT INTO journal_entry_lines (line_id, aje_id, account_id, amount, sort_order)
           VALUES (?,?,?,?,0)""",
        (line_id, aje_id, account_id, amount),
    )
    return aje_id


# ---------------------------------------------------------------------------
# Computed columns
# ---------------------------------------------------------------------------

def test_computed_adj(atbw_path):
    job = get_job(atbw_path)
    with db_connection(atbw_path) as conn:
        aid = _insert_account(conn, job["job_id"], name="Cash", balance=1000.0)
        _insert_aje(conn, job["job_id"], aid, 200.0, "AJE")
    with db_connection(atbw_path) as conn:
        accts = get_account_balances(conn, job["job_id"])
    acct = next(a for a in accts if a["account_id"] == aid)
    assert acct["pbc_balance"] == pytest.approx(1000.0)
    assert acct["aje"]         == pytest.approx(200.0)
    assert acct["adj"]         == pytest.approx(1200.0)


def test_computed_final(atbw_path):
    job = get_job(atbw_path)
    with db_connection(atbw_path) as conn:
        aid = _insert_account(conn, job["job_id"], name="AR", balance=5000.0)
        _insert_aje(conn, job["job_id"], aid, 100.0,  "AJE")
        _insert_aje(conn, job["job_id"], aid, -500.0, "RJE")
    with db_connection(atbw_path) as conn:
        accts = get_account_balances(conn, job["job_id"])
    acct = next(a for a in accts if a["account_id"] == aid)
    assert acct["adj"]   == pytest.approx(5100.0)
    assert acct["rje"]   == pytest.approx(-500.0)
    assert acct["final"] == pytest.approx(4600.0)


def test_computed_ftax(atbw_path):
    job = get_job(atbw_path)
    with db_connection(atbw_path) as conn:
        aid = _insert_account(conn, job["job_id"], name="Revenue", balance=-80000.0)
        _insert_aje(conn, job["job_id"], aid, -1000.0, "FTJE")
    with db_connection(atbw_path) as conn:
        accts = get_account_balances(conn, job["job_id"])
    acct = next(a for a in accts if a["account_id"] == aid)
    assert acct["final"] == pytest.approx(-80000.0)
    assert acct["ftje"]  == pytest.approx(-1000.0)
    assert acct["ftax"]  == pytest.approx(-81000.0)


def test_no_aje_columns_are_zero(atbw_path):
    job = get_job(atbw_path)
    with db_connection(atbw_path) as conn:
        _insert_account(conn, job["job_id"], name="Inventory", balance=3000.0)
    with db_connection(atbw_path) as conn:
        accts = get_account_balances(conn, job["job_id"])
    acct = next(a for a in accts if a["account_name"] == "Inventory")
    assert acct["aje"]  == 0.0
    assert acct["rje"]  == 0.0
    assert acct["ftje"] == 0.0
    assert acct["adj"]  == pytest.approx(3000.0)
    assert acct["ftax"] == pytest.approx(3000.0)


def test_rje_does_not_affect_adj(atbw_path):
    job = get_job(atbw_path)
    with db_connection(atbw_path) as conn:
        aid = _insert_account(conn, job["job_id"], name="Prepaid", balance=1000.0)
        _insert_aje(conn, job["job_id"], aid, 500.0, "RJE")
    with db_connection(atbw_path) as conn:
        accts = get_account_balances(conn, job["job_id"])
    acct = next(a for a in accts if a["account_id"] == aid)
    assert acct["adj"]   == pytest.approx(1000.0)   # RJE doesn't touch ADJ
    assert acct["final"] == pytest.approx(1500.0)


def test_ftje_does_not_affect_final(atbw_path):
    job = get_job(atbw_path)
    with db_connection(atbw_path) as conn:
        aid = _insert_account(conn, job["job_id"], name="PPE", balance=50000.0)
        _insert_aje(conn, job["job_id"], aid, 200.0, "FTJE")
    with db_connection(atbw_path) as conn:
        accts = get_account_balances(conn, job["job_id"])
    acct = next(a for a in accts if a["account_id"] == aid)
    assert acct["final"] == pytest.approx(50000.0)   # FTJE doesn't touch FINAL
    assert acct["ftax"]  == pytest.approx(50200.0)


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------

def test_unmapped_accounts_grouped_separately(atbw_path):
    job = get_job(atbw_path)
    with db_connection(atbw_path) as conn:
        _insert_account(conn, job["job_id"], name="Cash", balance=1000.0)
    with db_connection(atbw_path) as conn:
        groups = get_grouped_balances(conn, job["job_id"])
    assert "Unmapped" in groups
    assert any(a["account_name"] == "Cash" for a in groups["Unmapped"])


def test_section_subtotals(atbw_path):
    job = get_job(atbw_path)
    with db_connection(atbw_path) as conn:
        _insert_account(conn, job["job_id"], name="Cash",   balance=1000.0)
        _insert_account(conn, job["job_id"], name="AR",     balance=2000.0)
        _insert_account(conn, job["job_id"], name="Prepaid",balance=500.0)
    with db_connection(atbw_path) as conn:
        accts = get_account_balances(conn, job["job_id"])
    total_pbc = sum(a["pbc_balance"] for a in accts)
    assert total_pbc == pytest.approx(3500.0)


# ---------------------------------------------------------------------------
# Flags
# ---------------------------------------------------------------------------

def test_set_flag(atbw_path):
    job = get_job(atbw_path)
    with db_connection(atbw_path) as conn:
        aid = _insert_account(conn, job["job_id"], name="Cash", balance=1000.0)
    with db_connection(atbw_path) as conn:
        set_flag(conn, aid, "reviewed")
    with db_connection(atbw_path) as conn:
        row = conn.execute(
            "SELECT flag FROM accounts WHERE account_id = ?", (aid,)
        ).fetchone()
    assert row["flag"] == "reviewed"


def test_clear_flag(atbw_path):
    job = get_job(atbw_path)
    with db_connection(atbw_path) as conn:
        aid = _insert_account(conn, job["job_id"], name="Cash2", balance=500.0)
        set_flag(conn, aid, "issue")
    with db_connection(atbw_path) as conn:
        set_flag(conn, aid, None)
    with db_connection(atbw_path) as conn:
        row = conn.execute(
            "SELECT flag FROM accounts WHERE account_id = ?", (aid,)
        ).fetchone()
    assert row["flag"] is None
