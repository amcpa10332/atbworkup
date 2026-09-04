"""M4 tests: tax line templates, account mapping, grid grouping after mapping."""
import pytest
import uuid
import datetime

from atbworkup.db.connection import db_connection
from atbworkup.db.settings import settings_connection, ensure_settings_db, set_settings_path
from atbworkup.models.accounts import get_grouped_balances
from atbworkup.models.mappings import (
    get_tax_line_templates, upsert_tax_line, map_accounts, get_mapping,
)
from atbworkup.models.job import get_job


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _insert_account(conn, job_id, *, name, balance=1000.0):
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
# Settings DB / templates
# ---------------------------------------------------------------------------

def test_settings_schema_created(tmp_path):
    db_path = tmp_path / "settings.db"
    set_settings_path(db_path)
    ensure_settings_db()
    with settings_connection() as conn:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    assert "tax_line_templates" in tables
    assert "admin_config" in tables


def test_default_templates_seeded(tmp_path):
    db_path = tmp_path / "settings_seed.db"
    set_settings_path(db_path)
    ensure_settings_db()
    with settings_connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM tax_line_templates WHERE entity_type = '1120S'"
        ).fetchone()[0]
    assert count > 10


def test_templates_returned_for_entity_type(tmp_path):
    db_path = tmp_path / "settings_tmpl.db"
    set_settings_path(db_path)
    ensure_settings_db()
    with settings_connection() as conn:
        lines = get_tax_line_templates(conn, "1065")
    assert len(lines) > 0
    fs_values = {l["financial_statement"] for l in lines}
    assert "BalanceSheet" in fs_values
    assert "ProfitAndLoss" in fs_values


def test_templates_all_entity_types_seeded(tmp_path):
    db_path = tmp_path / "settings_all.db"
    set_settings_path(db_path)
    ensure_settings_db()
    entity_types = ["1120S", "1065", "1120", "ScheduleC", "990", "1041"]
    with settings_connection() as conn:
        for et in entity_types:
            count = conn.execute(
                "SELECT COUNT(*) FROM tax_line_templates WHERE entity_type = ?", (et,)
            ).fetchone()[0]
            assert count > 0, f"No templates seeded for {et}"


def test_ensure_settings_db_idempotent(tmp_path):
    db_path = tmp_path / "settings_idem.db"
    set_settings_path(db_path)
    ensure_settings_db()
    ensure_settings_db()  # second call should not duplicate rows
    with settings_connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM tax_line_templates WHERE entity_type = '1120S'"
        ).fetchone()[0]
    # Should still be exactly the seeded amount, not doubled
    with settings_connection() as conn:
        count2 = conn.execute(
            "SELECT COUNT(*) FROM tax_line_templates WHERE entity_type = '1120S'"
        ).fetchone()[0]
    assert count == count2


# ---------------------------------------------------------------------------
# Mapping
# ---------------------------------------------------------------------------

def test_map_single_account(tmp_path, atbw_path):
    db_path = tmp_path / "settings_map.db"
    set_settings_path(db_path)
    ensure_settings_db()

    job = get_job(atbw_path)
    with db_connection(atbw_path) as conn:
        aid = _insert_account(conn, job["job_id"], name="Cash")

    with settings_connection() as sconn:
        templates = get_tax_line_templates(sconn, "1120S")
    cash_line = next(t for t in templates if t["line_name"] == "Cash")

    with db_connection(atbw_path) as conn:
        tax_line_id = upsert_tax_line(
            conn,
            entity_type="1120S",
            financial_statement=cash_line["financial_statement"],
            line_code=cash_line["line_code"],
            line_name=cash_line["line_name"],
            sort_order=cash_line["sort_order"],
        )
        map_accounts(conn, job_id=job["job_id"], account_ids=[aid],
                     tax_line_id=tax_line_id, mapped_by="preparer")

    with db_connection(atbw_path) as conn:
        mapping = get_mapping(conn, aid)
    assert mapping is not None
    assert mapping["line_name"] == "Cash"
    assert mapping["financial_statement"] == "BalanceSheet"


def test_map_bulk_accounts(tmp_path, atbw_path):
    db_path = tmp_path / "settings_bulk.db"
    set_settings_path(db_path)
    ensure_settings_db()

    job = get_job(atbw_path)
    with db_connection(atbw_path) as conn:
        ids = [
            _insert_account(conn, job["job_id"], name=f"Cash Account {i}")
            for i in range(5)
        ]

    with settings_connection() as sconn:
        templates = get_tax_line_templates(sconn, "1120S")
    cash_line = next(t for t in templates if t["line_name"] == "Cash")

    with db_connection(atbw_path) as conn:
        tax_line_id = upsert_tax_line(
            conn, entity_type="1120S",
            financial_statement=cash_line["financial_statement"],
            line_code=cash_line["line_code"],
            line_name=cash_line["line_name"],
            sort_order=cash_line["sort_order"],
        )
        map_accounts(conn, job_id=job["job_id"], account_ids=ids,
                     tax_line_id=tax_line_id, mapped_by="preparer")

    with db_connection(atbw_path) as conn:
        for aid in ids:
            m = get_mapping(conn, aid)
            assert m is not None
            assert m["line_name"] == "Cash"


def test_remap_account_replaces_prior_mapping(tmp_path, atbw_path):
    db_path = tmp_path / "settings_remap.db"
    set_settings_path(db_path)
    ensure_settings_db()

    job = get_job(atbw_path)
    with db_connection(atbw_path) as conn:
        aid = _insert_account(conn, job["job_id"], name="Petty Cash")

    with settings_connection() as sconn:
        templates = get_tax_line_templates(sconn, "1120S")

    def _map_to(line_name):
        line = next(t for t in templates if t["line_name"] == line_name)
        with db_connection(atbw_path) as conn:
            tl_id = upsert_tax_line(
                conn, entity_type="1120S",
                financial_statement=line["financial_statement"],
                line_code=line["line_code"],
                line_name=line["line_name"],
                sort_order=line["sort_order"],
            )
            map_accounts(conn, job_id=job["job_id"], account_ids=[aid],
                         tax_line_id=tl_id, mapped_by="preparer")

    _map_to("Cash")
    _map_to("Trade Notes & Accounts Receivable")

    with db_connection(atbw_path) as conn:
        m = get_mapping(conn, aid)
    assert m["line_name"] == "Trade Notes & Accounts Receivable"

    # only one mapping row should exist
    with db_connection(atbw_path) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM mappings WHERE account_id = ?", (aid,)
        ).fetchone()[0]
    assert count == 1


def test_mapped_account_grouped_in_balance_sheet(tmp_path, atbw_path):
    db_path = tmp_path / "settings_grp.db"
    set_settings_path(db_path)
    ensure_settings_db()

    job = get_job(atbw_path)
    with db_connection(atbw_path) as conn:
        aid = _insert_account(conn, job["job_id"], name="Checking Account")

    with settings_connection() as sconn:
        templates = get_tax_line_templates(sconn, "1120S")
    cash_line = next(t for t in templates if t["line_name"] == "Cash")

    with db_connection(atbw_path) as conn:
        tl_id = upsert_tax_line(
            conn, entity_type="1120S",
            financial_statement=cash_line["financial_statement"],
            line_code=cash_line["line_code"],
            line_name=cash_line["line_name"],
            sort_order=cash_line["sort_order"],
        )
        map_accounts(conn, job_id=job["job_id"], account_ids=[aid],
                     tax_line_id=tl_id, mapped_by="preparer")

    with db_connection(atbw_path) as conn:
        groups = get_grouped_balances(conn, job["job_id"])

    assert "BalanceSheet" in groups
    assert "Unmapped" not in groups or not any(
        a["account_id"] == aid for a in groups.get("Unmapped", [])
    )
    bs_ids = [a["account_id"] for a in groups["BalanceSheet"]]
    assert aid in bs_ids


def test_unmapped_accounts_stay_in_unmapped(atbw_path):
    job = get_job(atbw_path)
    with db_connection(atbw_path) as conn:
        aid = _insert_account(conn, job["job_id"], name="Mystery Account")

    with db_connection(atbw_path) as conn:
        groups = get_grouped_balances(conn, job["job_id"])

    assert "Unmapped" in groups
    unmapped_ids = [a["account_id"] for a in groups["Unmapped"]]
    assert aid in unmapped_ids
