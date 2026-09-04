# TEST_PLAN.md — Trial Balance Workup Tool

## Philosophy

- Tests run locally, offline, with no Excel or Qt display required (headless).
- No mocking the database. Tests use a real temporary SQLite file.
- No mocking the filesystem. Tests use `tmp_path` (pytest fixture).
- UI logic is separated from business logic so core functions are testable without a display.
- Excel tests use real openpyxl reads on generated files.
- Tests are the primary quality gate before each milestone ships.

## Test Layout

```
tests/
  conftest.py              # shared fixtures: tmp .atbw path, sample TB xlsx
  test_m1_job.py           # M1: file creation, metadata, activity log
  test_m2_import.py        # M2: Excel TB import wizard logic
  test_m3_grid.py          # M3: financial statement query/aggregation
  test_m4_mapping.py       # M4: account mapping, tax line assignment
  test_m5_journal.py       # M5: journal entries, balance check, computed columns
  test_m6_notes.py         # M6: note creation, linking, status
  test_m7_export.py        # M7: export package structure, hidden tabs, checksum
  test_m8_import_pkg.py    # M8: re-import validation, lineage, conflict detection
  test_m9_reviewer.py      # M9: reviewer notes, resolve rules, role enforcement
  test_m10_workflow.py     # M10: full V01→V02→V03 cycle
  test_m11_final.py        # M11: finalization, lock, reopen
  test_m12_rollforward.py  # M12: roll-forward from prior year
  test_m13_diagnostics.py  # M13: diagnostic rules
  fixtures/
    sample_tb_single_col.xlsx
    sample_tb_two_col.xlsx
    sample_tb_parenthetical.xlsx
    sample_tb_messy_headers.xlsx
```

---

## App Settings Tests

### `test_user_profile_created_on_first_launch`
- Call `setup_user_profile(name, initials, email)`.
- Assert `atbw_settings.db` is created with one row in `user_profile`.

### `test_user_profile_roundtrip`
- Save profile; reload from settings db.
- Assert all fields match.

### `test_admin_password_set`
- Call `set_admin_password("secret")`.
- Assert `admin_settings.password_hash` is a bcrypt hash, not plaintext.

### `test_admin_password_verify`
- Set password "secret"; verify "secret" → True; verify "wrong" → False.

### `test_tax_line_edit_requires_admin`
- Call `add_tax_line(...)` without providing admin password.
- Assert raises `AdminAuthError`.

### `test_tax_line_edit_with_admin`
- Call `add_tax_line(..., admin_password="secret")`.
- Assert new tax line appears in `tax_lines` table in settings db.

### `test_role_selection_stored_in_session`
- Open binder; select role = Reviewer.
- Assert `session.role == 'Reviewer'`.
- Close and reopen binder; assert role prompt appears again (not remembered).

---

## M1 Tests — Native File + Job Metadata

### `test_create_atbw_file`
- Call `create_workup(path, metadata)`.
- Assert file exists at `path`.
- Assert file is a valid SQLite database.
- Assert `job` table exists and has exactly one row.
- Assert all required columns are present.

### `test_job_metadata_roundtrip`
- Create workup with known metadata.
- Close connection.
- Reopen file.
- Read `job` row.
- Assert each field matches input exactly.

### `test_schema_version_set`
- Create workup.
- Assert `job.schema_version == "1.0"`.

### `test_all_tables_created`
- Create workup.
- Assert all expected tables exist: `job`, `accounts`, `tax_lines`, `mappings`,
  `sections`, `journal_entries`, `journal_entry_lines`, `notes`, `signoffs`,
  `packages`, `activity_log`, `prior_year_balances`.

### `test_activity_log_on_create`
- Create workup.
- Query `activity_log` for `event_type = 'created_workup'`.
- Assert exactly one row; `performed_by` matches `prepared_by` from metadata.

### `test_activity_log_on_open`
- Create workup; close; reopen via `open_workup(path)`.
- Query `activity_log` for `event_type = 'opened_workup'`.
- Assert one new row added.

### `test_file_naming`
- Create workup with tax_year=2025, client_name="ABC Company".
- Assert suggested file name = `2025 ABC Company TB Workup.atbw`.

### `test_foreign_keys_enforced`
- Open connection with `PRAGMA foreign_keys = ON`.
- Attempt to insert an `accounts` row with a non-existent `job_id`.
- Assert `IntegrityError` is raised.

---

## M2 Tests — Excel TB Import

### `test_single_column_import`
- Load `sample_tb_single_col.xlsx`.
- Run import with correct column selections.
- Assert account count matches expected.
- Assert PBC balances match source to the cent.

### `test_two_column_import`
- Load `sample_tb_two_col.xlsx` (separate Dr/Cr columns).
- Assert debit-only accounts have positive PBC; credit-only accounts have negative PBC
  (or use sign convention appropriate to account type).

### `test_parenthetical_negatives`
- Load `sample_tb_parenthetical.xlsx` containing `(1,234.56)`.
- Assert parsed value = `-1234.56`.

### `test_header_auto_detection`
- Load `sample_tb_messy_headers.xlsx` (2 blank rows before header).
- Assert wizard detects the correct header row.

### `test_blank_rows_skipped`
- Load a TB with blank separator rows between sections.
- Assert blank rows are not inserted as accounts.

### `test_tb_balance_check`
- Import a balanced TB.
- Assert `SUM(pbc_balance where account_type in debit-normal) == SUM(pbc_balance where account_type in credit-normal)`.
- (Exact logic depends on sign convention chosen; test documents the expectation.)

### `test_accounts_written_unmapped`
- After import, query all `accounts` rows.
- Assert all have `is_mapped = 0`.

### `test_activity_log_on_import`
- Import a TB.
- Assert `activity_log` has `event_type = 'imported_tb'`.

---

## M3 Tests — Financial Statement Grid

### `test_accounts_by_financial_statement`
- Insert accounts of mixed types.
- Call `get_accounts_grouped()`.
- Assert Balance Sheet accounts are separated from P&L accounts.

### `test_computed_adj`
- Insert an account with `pbc_balance = 1000`.
- Insert an AJE line for that account: `debit = 200`.
- Assert `get_adj(account_id) == 1200` (or 800, depending on sign convention).

### `test_computed_final`
- Insert AJE and RJE lines.
- Assert FINAL = ADJ + RJE net.

### `test_computed_ftax`
- Insert FTJE lines.
- Assert FTAX = FINAL + FTJE net.

### `test_section_subtotals`
- Insert 3 accounts in the same section.
- Assert section subtotal = sum of individual account computed balances.

### `test_unmapped_accounts_grouped_separately`
- Insert one mapped and one unmapped account.
- Assert unmapped account appears in an "Unmapped" group.

---

## M4 Tests — Account Mapping

### `test_map_single_account`
- Import accounts; map one account to a tax_line.
- Assert `mappings` table has one row with correct `account_id` and `tax_line_id`.
- Assert `accounts.is_mapped = 1` for that account.

### `test_bulk_mapping`
- Select 5 accounts; call `map_accounts([ids], tax_line_id, section_id)`.
- Assert all 5 accounts mapped.

### `test_remap_account`
- Map an account to line A; remap to line B.
- Assert `mappings` row now shows line B.
- Assert `activity_log` has two `changed_mapping` events.

### `test_tax_line_templates_by_entity_type`
- Load tax lines for `1120S`.
- Assert Balance Sheet lines and P&L lines are returned in correct order.
- Repeat for `1065`.

### `test_unknown_mapping_blocked_on_export`
- Leave one account unmapped.
- Call export validation.
- Assert validation returns an error listing the unmapped account.

---

## M5 Tests — Journal Entries

### `test_create_balanced_aje`
- Create AJE with debit line $500 and credit line $500 on two accounts.
- Assert `journal_entries.is_balanced = 1`.

### `test_create_unbalanced_aje`
- Create AJE with only a debit line $500 (no credit).
- Assert `journal_entries.is_balanced = 0`.

### `test_shell_entry_status`
- Create shell entry via grid `+`.
- Assert `journal_entries.status = 'Shell'`.

### `test_adj_updates_on_aje_add`
- Account has `pbc_balance = 1000`.
- Add AJE debit $200 to that account.
- Assert `get_adj(account_id) == 1200`.

### `test_adj_updates_on_aje_delete`
- Add then delete an AJE.
- Assert ADJ returns to PBC value.

### `test_aje_numbering`
- Create three AJEs.
- Assert entry_numbers are `AJE-001`, `AJE-002`, `AJE-003`.

### `test_rje_does_not_affect_adj`
- Add RJE to an account.
- Assert ADJ is unchanged; FINAL changes.

### `test_ftje_does_not_affect_final`
- Add FTJE to an account.
- Assert FINAL is unchanged; FTAX changes.

---

## M6 Tests — Notes and Flags

### `test_create_preparer_note_linked_to_account`
- Create note with `linked_to_type = 'account'` and valid `account_id`.
- Query notes; assert one row with correct fields.

### `test_create_general_note`
- Create note with `linked_to_type = 'general'`.
- Assert `linked_to_id IS NULL`.

### `test_open_notes_count`
- Create 3 notes; resolve 1.
- Assert `get_open_notes_count() == 2`.

### `test_flag_cycle`
- Set account flag to `reviewed`; then to `issue`; then to NULL.
- Assert `accounts.flag` changes correctly each time.

---

## M7 Tests — Export Review Package

### `test_export_creates_file`
- Run all validations on a valid workup.
- Export package.
- Assert file exists at expected path with auto-generated name.

### `test_hidden_tabs_present`
- Open exported `.atbr.xlsx` with openpyxl.
- Assert all `__` sheets exist.

### `test_hidden_tabs_very_hidden`
- Open exported file.
- For each `__` sheet: assert `sheet_state == 'veryHidden'`.

### `test_manifest_fields`
- Read `__manifest` tab.
- Assert all required fields are present and non-empty.
- Assert `version_number == 1`.

### `test_checksum_valid`
- Read `__manifest.checksum`.
- Recompute checksum from `__` tabs.
- Assert they match.

### `test_accounts_in_hidden_tab`
- Read `__accounts` tab.
- Assert row count matches `accounts` table row count.
- Assert `account_id` column values match.

### `test_validation_blocks_unmapped`
- Leave accounts unmapped.
- Call export validation.
- Assert validation fails; no file is created.

### `test_package_record_written`
- Export package.
- Assert `packages` table has one row with correct `version_number` and `file_name`.

### `test_file_name_format`
- Export package.
- Assert file name matches pattern:
  `YYYY Client Name TB Workup - V01 - Ready for Review - YYYYMMDD-HHMM.atbr.xlsx`.

---

## M8 Tests — Import Review Package

### `test_valid_import_accepted`
- Export V01; simulate reviewer changes in hidden tabs; re-import.
- Assert reviewer notes appear in `notes` table.

### `test_wrong_job_id_rejected`
- Modify `__manifest.job_id` in the file.
- Assert import raises a descriptive error.

### `test_wrong_version_rejected`
- Export V01; try to import as if it were V02 (set version to 3).
- Assert lineage validation fails.

### `test_broken_checksum_rejected`
- Export V01; corrupt one byte in a `__` tab; re-import.
- Assert checksum validation fails and import is blocked.

### `test_reviewer_changes_tagged`
- Import a package with reviewer-added AJEs.
- Assert `journal_entries.originated_by = 'reviewer'` for those entries.

### `test_conflict_detected`
- Export V01.
- Make a local mapping change to account X in `.atbw`.
- Import a response where reviewer also changed mapping for account X.
- Assert conflict is detected (not silently overwritten).

---

## M9 Tests — Reviewer UI and Note Rules

### `test_reviewer_can_create_review_note`
- In reviewer mode, create a review note.
- Assert `notes.note_type = 'review'`.

### `test_preparer_cannot_resolve_review_note`
- Create a review note.
- Call `resolve_note(note_id, role='preparer')`.
- Assert `PermissionError` (or equivalent) is raised.

### `test_reviewer_can_resolve_review_note`
- Create a review note.
- Call `resolve_note(note_id, role='reviewer')`.
- Assert `notes.status = 'Resolved'`.

### `test_preparer_can_clear_review_note`
- Create a review note.
- Call `clear_note(note_id, role='preparer', response='Corrected.')`.
- Assert `notes.status = 'Cleared'` and `notes.cleared_by` is set.

### `test_reviewer_flag_only_in_reviewer_mode`
- In preparer mode, attempt to set purple R flag.
- Assert flag is not applied (no-op or error).

---

## M10 Tests — Versioned Workflow

### `test_full_v01_v02_v03_cycle`
- Create workup → import TB → map accounts → create AJE → export V01.
- Simulate reviewer response → import V02.
- Clear notes → export V03.
- Assert: 3 rows in `packages`; version numbers 1, 2, 3; prior_package_id chain correct.

### `test_status_transitions`
- Assert status = `In Prep` after TB import.
- Assert status = `Ready for Review` after V01 export.
- Assert status = `Reviewer Notes` after V02 import.
- Assert status = `Cleared for Review` after V03 export.

### `test_out_of_order_import_rejected`
- Export V01; skip V02; try to import a fake V03.
- Assert lineage validation fails.

---

## M11 Tests — Finalization

### `test_finalization_creates_files`
- Run full cycle to `Ready for Final Review`.
- Call `finalize()`.
- Assert `FINAL.xlsx` and `FINAL.pdf` exist in workpaper folder.

### `test_job_locked_after_finalization`
- Call `finalize()`.
- Assert `job.status = 'Final'` and `job.finalized_at` is set.

### `test_reopen_requires_reason`
- Finalize workup.
- Call `reopen_workup(reason='')`.
- Assert raises `ValueError` (blank reason not allowed).

### `test_reopen_logs_event`
- Finalize; reopen with reason "Client sent corrected K-1."
- Assert `activity_log` has `event_type = 'reopened_finalized'` with reason in `description`.

### `test_activity_log_in_final_xlsx`
- Open `FINAL.xlsx` with openpyxl.
- Assert `__activity_log` sheet exists and is `veryHidden`.
- Assert row count matches `activity_log` table row count.

---

## M12 Tests — Roll-Forward

### `test_rollforward_copies_mappings`
- Create and finalize a PY workup.
- Create new workup as roll-forward from PY file.
- Assert `mappings` table is pre-populated with PY mappings.

### `test_rollforward_copies_sections`
- Assert `sections` table is pre-populated from PY.

### `test_rollforward_does_not_copy_active_notes`
- PY workup has 3 open notes.
- Roll forward.
- Assert new workup has 0 open notes.

### `test_rollforward_brings_py_balances`
- Assert `prior_year_balances` is populated from PY FINAL and FTAX.

---

## M13 Tests — Diagnostics

### `test_diagnostic_unmapped_accounts`
- Leave 2 accounts unmapped.
- Run diagnostics.
- Assert result contains `unmapped_accounts` with count = 2.

### `test_diagnostic_tb_out_of_balance`
- Insert accounts that do not balance.
- Run diagnostics.
- Assert result contains `tb_out_of_balance`.

### `test_diagnostic_negative_cash`
- Insert Cash account with negative ADJ.
- Run diagnostics.
- Assert result contains `negative_cash`.

### `test_diagnostic_large_py_variance`
- Insert account where current FINAL differs from PY by > threshold.
- Run diagnostics.
- Assert result contains `large_py_variance` for that account.

---

## Running Tests

```bash
# Install dependencies
pip install -r requirements-dev.txt

# Run all tests
pytest

# Run a specific milestone
pytest tests/test_m1_job.py

# Run with coverage
pytest --cov=src --cov-report=term-missing

# Run without display (headless — all core tests should pass without a display)
pytest -m "not ui"
```

## CI Notes

- All tests in `tests/` must pass without a display (`QT_QPA_PLATFORM=offscreen` if needed
  for any Qt-touching tests, but prefer keeping UI and logic separated so core tests need
  no Qt at all).
- No internet access required.
- No Excel installation required (openpyxl only).
- Test fixtures (sample `.xlsx` files) are committed to the repo under `tests/fixtures/`.
