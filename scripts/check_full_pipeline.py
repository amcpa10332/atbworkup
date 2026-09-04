"""
Diagnostic: full pipeline — create workup, save_workup, open_from_package.
Run: python scripts/check_full_pipeline.py
"""
import hashlib
import sys
import tempfile
import uuid
from pathlib import Path

# Bootstrap settings DB
from atbworkup.db.settings import ensure_settings_db, set_settings_path
from atbworkup.db.connection import db_connection
from atbworkup.models.job import create_workup, get_job
from atbworkup.models.mappings import upsert_tax_line, map_accounts
from atbworkup.exporter.review_package import save_workup
from atbworkup.importer.package import open_from_package
from atbworkup.utils.naming import temp_atbw_path
import datetime, openpyxl, json

tmp = Path(tempfile.mkdtemp())
set_settings_path(tmp / "settings.db")
ensure_settings_db()

# --- 1. Create a binder ---
meta = {
    "client_name": "Austin & Partners LLC",  # & is XML-special
    "entity_name": "Austin Partners",
    "tax_year": 2024,
    "entity_type": "1120S",
    "prepared_by": "Austin Malone",
    "reviewer": None,
    "workpaper_folder": str(tmp),
    "accounting_system": "QuickBooks",
}
job_id = uuid.uuid4().hex
atbw = tmp / "work.atbw"
create_workup(atbw, meta, job_id=job_id)
job = get_job(atbw)

now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
with db_connection(atbw) as conn:
    # Add two accounts
    a1 = uuid.uuid4().hex
    a2 = uuid.uuid4().hex
    for aid, name, bal in [(a1, "Cash", 5000.0), (a2, "Capital", -5000.0)]:
        conn.execute(
            "INSERT INTO accounts (account_id,job_id,account_number,account_name,account_type,"
            "pbc_balance,normal_balance,sort_order,is_mapped,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,0,0,?,?)",
            (aid, job_id, "1000" if bal > 0 else "3000", name, "Asset", bal, "Debit", now, now),
        )
    # Add tax lines and map
    upsert_tax_line(conn, entity_type="1120S", financial_statement="BalanceSheet",
                    line_code="BS-01", line_name="Cash", sort_order=10)
    upsert_tax_line(conn, entity_type="1120S", financial_statement="BalanceSheet",
                    line_code="BS-50", line_name="Equity", sort_order=50)
    tl1 = conn.execute("SELECT tax_line_id FROM tax_lines WHERE line_code='BS-01' AND entity_type='1120S'").fetchone()["tax_line_id"]
    tl2 = conn.execute("SELECT tax_line_id FROM tax_lines WHERE line_code='BS-50' AND entity_type='1120S'").fetchone()["tax_line_id"]
    map_accounts(conn, job_id=job_id, account_ids=[a1], tax_line_id=tl1, mapped_by="preparer")
    map_accounts(conn, job_id=job_id, account_ids=[a2], tax_line_id=tl2, mapped_by="preparer")

print("Step 1: Binder created")

# --- 2. save_workup ---
xlsx = tmp / "output.atbr.xlsx"
with db_connection(atbw) as conn:
    save_workup(conn, job=job, output_path=xlsx, performed_by="Austin Malone")
print(f"Step 2: Saved to {xlsx}")

# --- 3. Read __data and __manifest directly ---
wb = openpyxl.load_workbook(str(xlsx), data_only=True)
data_content = ""
for row in wb["__data"].iter_rows(min_row=1, max_row=1, values_only=True):
    if row and row[0] is not None:
        data_content = str(row[0])
manifest = {}
for row in wb["__manifest"].iter_rows(values_only=True):
    if row and row[0]:
        manifest[str(row[0])] = str(row[1]) if row[1] is not None else ""

stored = manifest.get("checksum_sha256", "")
actual = hashlib.sha256(data_content.encode("utf-8")).hexdigest()
print(f"\nStep 3: Direct read")
print(f"  Data len  : {len(data_content)}")
print(f"  Stored    : {stored}")
print(f"  Computed  : {actual}")
print(f"  Match     : {stored == actual}")
if stored != actual:
    print(f"  Data[:120]: {data_content[:120]}")

# --- 4. open_from_package ---
try:
    temp_path, reopened_job = open_from_package(xlsx, performed_by="Reviewer")
    print(f"\nStep 4: open_from_package SUCCESS")
    print(f"  client_name: {reopened_job['client_name']}")
    print(f"  job_id match: {reopened_job['job_id'] == job_id}")
    temp_path.unlink(missing_ok=True)
except ValueError as e:
    print(f"\nStep 4: open_from_package FAILED")
    print(f"  Error: {e}")
    sys.exit(1)

# cleanup
import shutil
shutil.rmtree(str(tmp))
print("\nAll checks passed.")
sys.exit(0)
