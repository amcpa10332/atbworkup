"""M2 tests: Excel TB import parser and writer."""
from pathlib import Path

import pytest

from atbworkup.importer.tb_parser import (
    get_sheet_names, read_raw_rows, detect_header_row,
    parse_accounts, _try_parse_amount,
)
from atbworkup.importer.tb_writer import write_accounts
from atbworkup.db.connection import db_connection
from atbworkup.models.job import get_activity_log, get_job


FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Amount parsing
# ---------------------------------------------------------------------------

def test_parse_positive():
    val, ok = _try_parse_amount("1234.56")
    assert ok and val == pytest.approx(1234.56)

def test_parse_comma_formatted():
    val, ok = _try_parse_amount("1,234.56")
    assert ok and val == pytest.approx(1234.56)

def test_parse_negative():
    val, ok = _try_parse_amount("-1234.56")
    assert ok and val == pytest.approx(-1234.56)

def test_parse_parenthetical():
    val, ok = _try_parse_amount("(1,234.56)")
    assert ok and val == pytest.approx(-1234.56)

def test_parse_parenthetical_no_comma():
    val, ok = _try_parse_amount("(50000.00)")
    assert ok and val == pytest.approx(-50000.00)

def test_parse_empty_string():
    val, ok = _try_parse_amount("")
    assert not ok

def test_parse_text():
    val, ok = _try_parse_amount("Account Name")
    assert not ok


# ---------------------------------------------------------------------------
# Sheet names
# ---------------------------------------------------------------------------

def test_get_sheet_names_single_col():
    sheets = get_sheet_names(FIXTURES / "sample_tb_single_col.xlsx")
    assert "TB" in sheets


# ---------------------------------------------------------------------------
# Single-column layout
# ---------------------------------------------------------------------------

def test_single_col_account_count():
    rows = read_raw_rows(FIXTURES / "sample_tb_single_col.xlsx", "TB")
    result = parse_accounts(rows, header_row=0, name_col=1, number_col=0, balance_col=2)
    assert len(result.accounts) == 6

def test_single_col_balances_accurate():
    rows = read_raw_rows(FIXTURES / "sample_tb_single_col.xlsx", "TB")
    result = parse_accounts(rows, header_row=0, name_col=1, number_col=0, balance_col=2)
    by_num = {a.account_number: a.pbc_balance for a in result.accounts}
    assert by_num["1000"] == pytest.approx(50000.00)
    assert by_num["2000"] == pytest.approx(-20000.00)

def test_single_col_is_balanced():
    rows = read_raw_rows(FIXTURES / "sample_tb_single_col.xlsx", "TB")
    result = parse_accounts(rows, header_row=0, name_col=1, number_col=0, balance_col=2)
    assert result.is_balanced

def test_single_col_totals():
    rows = read_raw_rows(FIXTURES / "sample_tb_single_col.xlsx", "TB")
    result = parse_accounts(rows, header_row=0, name_col=1, number_col=0, balance_col=2)
    assert result.total_debits == pytest.approx(140000.00)
    assert result.total_credits == pytest.approx(-140000.00)


# ---------------------------------------------------------------------------
# Two-column layout
# ---------------------------------------------------------------------------

def test_two_col_account_count():
    rows = read_raw_rows(FIXTURES / "sample_tb_two_col.xlsx", "TB")
    result = parse_accounts(rows, header_row=0, name_col=1, number_col=0,
                            debit_col=2, credit_col=3)
    assert len(result.accounts) == 6

def test_two_col_dr_positive():
    rows = read_raw_rows(FIXTURES / "sample_tb_two_col.xlsx", "TB")
    result = parse_accounts(rows, header_row=0, name_col=1, number_col=0,
                            debit_col=2, credit_col=3)
    by_num = {a.account_number: a.pbc_balance for a in result.accounts}
    assert by_num["1000"] == pytest.approx(50000.00)   # debit only → positive

def test_two_col_cr_negative():
    rows = read_raw_rows(FIXTURES / "sample_tb_two_col.xlsx", "TB")
    result = parse_accounts(rows, header_row=0, name_col=1, number_col=0,
                            debit_col=2, credit_col=3)
    by_num = {a.account_number: a.pbc_balance for a in result.accounts}
    assert by_num["2000"] == pytest.approx(-20000.00)  # credit only → negative

def test_two_col_is_balanced():
    rows = read_raw_rows(FIXTURES / "sample_tb_two_col.xlsx", "TB")
    result = parse_accounts(rows, header_row=0, name_col=1, number_col=0,
                            debit_col=2, credit_col=3)
    assert result.is_balanced


# ---------------------------------------------------------------------------
# Parenthetical negatives
# ---------------------------------------------------------------------------

def test_parenthetical_import():
    rows = read_raw_rows(FIXTURES / "sample_tb_parenthetical.xlsx", "TB")
    result = parse_accounts(rows, header_row=0, name_col=1, number_col=0, balance_col=2)
    by_num = {a.account_number: a.pbc_balance for a in result.accounts}
    assert by_num["1000"] == pytest.approx(50000.00)
    assert by_num["2000"] == pytest.approx(-50000.00)

def test_parenthetical_is_balanced():
    rows = read_raw_rows(FIXTURES / "sample_tb_parenthetical.xlsx", "TB")
    result = parse_accounts(rows, header_row=0, name_col=1, number_col=0, balance_col=2)
    assert result.is_balanced


# ---------------------------------------------------------------------------
# Header auto-detection
# ---------------------------------------------------------------------------

def test_header_auto_detect_messy():
    rows = read_raw_rows(FIXTURES / "sample_tb_messy_headers.xlsx", "TB")
    # name col is col 1 (B); header row is 0-based row 2
    detected = detect_header_row(rows, name_col=1)
    assert detected == 2


def test_header_detect_keyword_priority():
    """Keyword match (Debit/Credit) beats first-string-row fallback."""
    rows = [
        ["Precision Metal Works, Inc.", None, None, None],  # row 0 — title
        ["Trial Balance", None, None, None],                # row 1 — subtitle
        [None, None, None, None],                           # row 2 — blank
        ["Account", "Acct. No.", "Debit", "Credit"],        # row 3 — real header
        ["Cash", "1010", 45000, None],
    ]
    detected = detect_header_row(rows, name_col=0)
    assert detected == 3

def test_messy_headers_correct_account_count():
    rows = read_raw_rows(FIXTURES / "sample_tb_messy_headers.xlsx", "TB")
    # header_row=2 means rows 0,1,2 are skipped (pre-header + header itself)
    result = parse_accounts(rows, header_row=2, name_col=1, number_col=0, balance_col=2)
    assert len(result.accounts) == 2


# ---------------------------------------------------------------------------
# Accounts written unmapped
# ---------------------------------------------------------------------------

def test_accounts_written_unmapped(atbw_path):
    from atbworkup.models.job import get_job
    rows = read_raw_rows(FIXTURES / "sample_tb_single_col.xlsx", "TB")
    result = parse_accounts(rows, header_row=0, name_col=1, number_col=0, balance_col=2)
    job = get_job(atbw_path)
    with db_connection(atbw_path) as conn:
        write_accounts(conn, job_id=job["job_id"], result=result, performed_by="tester")
        rows_db = conn.execute(
            "SELECT is_mapped FROM accounts WHERE job_id = ?", (job["job_id"],)
        ).fetchall()
    assert len(rows_db) == 6
    assert all(r["is_mapped"] == 0 for r in rows_db)


def test_activity_log_on_import(atbw_path):
    rows = read_raw_rows(FIXTURES / "sample_tb_single_col.xlsx", "TB")
    result = parse_accounts(rows, header_row=0, name_col=1, number_col=0, balance_col=2)
    job = get_job(atbw_path)
    with db_connection(atbw_path) as conn:
        write_accounts(conn, job_id=job["job_id"], result=result, performed_by="tester")
    log = get_activity_log(atbw_path)
    events = [e["event_type"] for e in log]
    assert "imported_tb" in events


def test_status_unchanged_after_import(atbw_path):
    """Importing a TB is not a workflow transition — status stays put until
    the preparer explicitly submits for review."""
    rows = read_raw_rows(FIXTURES / "sample_tb_single_col.xlsx", "TB")
    result = parse_accounts(rows, header_row=0, name_col=1, number_col=0, balance_col=2)
    job = get_job(atbw_path)
    with db_connection(atbw_path) as conn:
        write_accounts(conn, job_id=job["job_id"], result=result, performed_by="tester")
    job2 = get_job(atbw_path)
    assert job2["status"] == "Preparation in Progress"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_no_balance_col_raises():
    rows = read_raw_rows(FIXTURES / "sample_tb_single_col.xlsx", "TB")
    with pytest.raises(ValueError, match="balance_col"):
        parse_accounts(rows, header_row=0, name_col=1)

def test_blank_name_rows_skipped():
    rows = [
        ["Acct#", "Name", "Balance"],
        ["1000",  "Cash",  50000],
        ["",      "",      None],   # blank — should be skipped
        ["2000",  "AP",   -50000],
    ]
    result = parse_accounts(rows, header_row=0, name_col=1, number_col=0, balance_col=2)
    assert len(result.accounts) == 2
    assert result.skipped_rows >= 1
