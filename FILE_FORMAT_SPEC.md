# FILE_FORMAT_SPEC.md — Trial Balance Workup Tool

---

## 1. Native Workup File (`.atbw`)

**What it is:** A SQLite database with a renamed extension.

**How to open:** `sqlite3.connect("path/to/file.atbw")` — no special driver needed.

**Naming:** `YYYY Client Name TB Workup.atbw`
Example: `2025 ABC Company TB Workup.atbw`

**Contents:** All tables defined in DATA_MODEL.md.

**Portability:** The file is fully self-contained. Copy it anywhere, open it on any machine
with the app installed. No server, no companion files required.

**Identification:** Every `.atbw` file has a `job` table with exactly one row. The app
validates this on open before displaying any data.

---

## 2. Review Exchange Package (`.atbr.xlsx`)

**What it is:** An Excel workbook that is both human-readable and machine-readable.

**Naming (app-controlled, no manual override):**
```
YYYY Client Name TB Workup - V01 - Ready for Review - YYYYMMDD-HHMM.atbr.xlsx
YYYY Client Name TB Workup - V02 - Reviewer Notes - YYYYMMDD-HHMM.atbr.xlsx
YYYY Client Name TB Workup - V03 - Cleared for Review - YYYYMMDD-HHMM.atbr.xlsx
```

### 2a. Visible (Human-Readable) Tabs

These tabs are for preparers and reviewers to read. They are regenerated from metadata
on each export. The app does NOT parse these tabs for data import.

| Tab Name | Contents |
|----------|----------|
| `Cover` | Job metadata, version, status, exported by/at |
| `Review Dashboard` | Outstanding notes, section statuses, diagnostics |
| `Mapped TB` | All accounts with tax line mapping |
| `Adjusted TB` | PBC / AJE / ADJ / RJE / FINAL / FTJE / FTAX columns |
| `AJEs` | All journal entries with line detail |
| `Tax Group Summary` | Balances rolled up by tax line |
| `Workpaper Sections` | Section list with status and preparer/reviewer signoff |
| `Review Notes` | All open notes with status, linked account/AJE |
| `Diagnostics` | Validation results, unmapped accounts, balance checks |

### 2b. Hidden (Machine-Readable) Tabs

These tabs are the actual data source the app reads on import. They are structured tables
with a header row and one data row per record. The app uses these, not the visible tabs.

All hidden tabs use sheet visibility = `xlSheetVeryHidden` (not just hidden — users cannot
unhide them from the Excel UI without a macro).

| Tab Name | Primary Key | Contents |
|----------|-------------|----------|
| `__manifest` | — | Package-level metadata (one row) |
| `__job` | `job_id` | Job metadata snapshot |
| `__accounts` | `account_id` | All accounts with PBC balance |
| `__mappings` | `mapping_id` | Account → tax_line + section mappings |
| `__ajes` | `aje_id` | Journal entry headers |
| `__aje_lines` | `line_id` | Journal entry detail lines |
| `__sections` | `section_id` | Workpaper sections with status |
| `__notes` | `note_id` | All notes with status |
| `__signoffs` | `signoff_id` | Signoff records |
| `__activity_log` | `activity_id` | Full activity log to that point |
| `__export_history` | `package_id` | All prior package records |

### 2c. `__manifest` Tab Structure

One data row. Validates the file before any other tab is read.

| Column | Example |
|--------|---------|
| `manifest_version` | `1` |
| `app_version` | `0.1.0` |
| `schema_version` | `1.0` |
| `job_id` | UUID |
| `package_id` | UUID |
| `version_number` | `1` |
| `package_type` | `review` |
| `status_label` | `Ready for Review` |
| `exported_by` | `Austin Malone` |
| `exported_at` | `2026-02-15T14:35:00Z` |
| `prior_package_id` | UUID or empty |
| `checksum_scope` | `hidden_tabs` |
| `checksum` | SHA-256 hex |

### 2d. Import Validation Rules

When the app opens a `.atbr.xlsx` file, it:

1. Reads `__manifest`. If missing or malformed → reject with error.
2. Validates `manifest_version` is supported by this app version.
3. Validates `job_id` matches the currently open `.atbw` file (or offers to create new).
4. Validates `version_number` is `current_max_version + 1` (lineage check).
5. Validates `prior_package_id` matches the last exported package in `packages` table.
6. Validates the SHA-256 checksum of all `__` tabs against `__manifest.checksum`.
7. If any check fails → show a descriptive error panel, do NOT silently import.

### 2e. Merge / Conflict Screen

If the incoming package contains reviewer-proposed changes that conflict with local
changes made since the package was exported, the app displays a side-by-side merge screen.
No silent overwrites.

---

## 3. Final Excel Binder (`FINAL.xlsx`)

**Naming:** `YYYY Client Name TB Workup - FINAL.xlsx`

**Contents:**

| Tab Name | Contents |
|----------|----------|
| `Cover` | Job info, finalized by/at, all signoffs |
| `Adjusted TB` | Full column set: PBC/AJE/ADJ/RJE/FINAL/FTJE/FTAX |
| `AJEs` | All finalized journal entries |
| `Tax Group Summary` | Rolled-up balances by tax line |
| `Workpaper Sections` | Final section statuses |
| `Review Notes` | All notes (resolved/cleared) with full history |
| `Diagnostics` | Final diagnostic results |
| `__activity_log` | Very hidden; full audit trail |
| `__job` | Very hidden; final job metadata snapshot |

**Lock status:** Generated once. Not editable through the app after finalization.
Reopening a finalized `.atbw` requires a logged reason; does not overwrite `FINAL.xlsx`.

---

## 4. Final PDF (`FINAL.pdf`)

**Naming:** `YYYY Client Name TB Workup - FINAL.pdf`

**Contents:** Financial statements and journal entries formatted for delivery. No audit log,
no hidden metadata. Generated from structured data using reportlab.

**Sections:**
- Cover page (client, entity, tax year, preparer, reviewer)
- Balance Sheet (FINAL and FTAX columns)
- Profit & Loss (FINAL and FTAX columns)
- Adjusting Journal Entries
- Reclassifying Journal Entries
- Federal Tax Journal Entries

**Non-editable:** The app only generates PDFs. It never reads or edits them.

---

## 5. Excel Trial Balance Import Format

The app does not require a specific format. The import wizard handles varied layouts.

**Sign convention after import:** All imported balances are stored as a single signed
number following the app's convention: debits positive, credits negative. If the source
TB uses a two-column layout (Dr/Cr), the wizard combines them: `amount = debit - credit`.
If the source uses a single signed column, the wizard maps the sign directly.

**Supported layouts:**

| Layout | Description |
|--------|-------------|
| Single balance column | One numeric column; positive = DR, negative = CR |
| Two-column (Dr/Cr) | Separate debit and credit columns; combined as `DR - CR` |

**Import wizard steps:**

1. User selects the `.xlsx` or `.xls` file.
2. App shows a preview grid of the first 30 rows.
3. User selects:
   - Header row (auto-detected, adjustable)
   - Account number column (optional)
   - Account name column (required)
   - Balance column(s) (required; one or two)
4. App previews the parsed accounts with running debit/credit totals.
5. User confirms import. Accounts are written to `accounts` table with status `unmapped`.

**Handled edge cases:**

- Subtotal/header rows (detected by blank account number + no balance)
- Negative numbers in parentheses: `(1,234.56)`
- Comma-formatted numbers
- Blank rows between sections
- Sheet selection if the workbook has multiple sheets

---

## 6. File Integrity

- Every `.atbr.xlsx` export has a SHA-256 checksum in `__manifest`.
- Checksum covers the serialized content of all `__` tabs (not visible tabs).
- On import, checksum is recomputed and compared. Mismatch → reject with error.
- `.atbw` files are not checksummed but the SQLite journal provides write-ahead logging.
- Users should not manually rename package files. The app validates the file name matches
  the `__manifest` on import (warning, not hard block, to handle copy/rename edge cases).
