# PROJECT_SPEC.md — Trial Balance Workup Tool

## 1. Purpose

An internal desktop application for an accounting firm to support trial balance workup,
prep/review workflow, and final workpaper export. It replaces TallyFor with a simpler,
faster, local-first tool that matches how the firm actually prepares and reviews tax workpapers.

## 2. Stack

| Component | Choice | Reason |
|-----------|--------|--------|
| Language | Python 3.11+ | Firm standard; good ecosystem |
| UI | PySide6 | Qt-native; works on Windows; no web server |
| Database | SQLite (via `sqlite3`) | File-based; portable; zero-config |
| Excel I/O | openpyxl | No COM dependency; runs headless |
| PDF output | reportlab | Programmatic; no LibreOffice dependency |
| Testing | pytest | Standard; fast; works offline |
| Packaging | PyInstaller (post-MVP) | Single-file EXE for firm machines |

No cloud sync. No web server. No multi-user simultaneous editing.

## 3. Native File Format

Extension: `.atbw`
Encoding: SQLite database (renamed file, not a ZIP)
Naming: `YYYY Client Name TB Workup.atbw`

The SQLite database is the sole source of truth. Excel files are export artifacts only.

## 4. Entity Types Supported

| Module | Form |
|--------|------|
| S-Corporation | 1120-S |
| Partnership | 1065 |
| C-Corporation | 1120 |
| Sole Proprietorship | Schedule C |
| Not-for-Profit | 990 |
| Trust or Estate | 1041 |

Each entity type has its own Balance Sheet and Profit & Loss line items. These are stored
as configurable templates, not hard-coded, so they can be updated each tax year.

## 5. Core Workflow

```
Create/Open .atbw
      │
      ▼
Import Excel TB (wizard)
      │
      ▼
Map accounts → tax lines / workpaper sections
      │
      ▼
Preparer workup (AJEs, RJEs, FTJEs, notes, flags)
      │
      ▼
Validate → Export Review Package (.atbr.xlsx V01)
      │
      ▼
Reviewer opens package → edits, adds notes, exports response (V02)
      │
      ▼
Preparer imports V02 → clears notes → exports V03
      │
      ▼
(repeats until finalized)
      │
      ▼
Finalize → FINAL.xlsx + FINAL.pdf
```

## 6. Sign Convention

**All amounts are stored and displayed as a single signed number.**

- Debits are **positive**.
- Credits are **negative**.

This applies to `pbc_balance` in `accounts`, to the `amount` field in
`journal_entry_lines`, and to all display columns in the financial statement grid.

A balanced trial balance: `SUM(pbc_balance) == 0` across all accounts.
A balanced journal entry: `SUM(amount) == 0` across all lines.

Totals and subtotals sum directly with no sign flipping. The grid displays one amount
column per financial statement column (PBC, AJE, ADJ, etc.).

## 7. Financial Statement Columns

| Column | Label | Description |
|--------|-------|-------------|
| PBC | Provided by Client | Raw imported balance (DR+, CR−) |
| AJE | Adjusting Journal Entry | Net AJE impact on this account |
| ADJ | Adjusted Book Balance | PBC + AJE |
| RJE | Reclassifying Journal Entry | Net RJE impact |
| FINAL | Final Book Balance | ADJ + RJE |
| FTJE | Federal Tax Journal Entry | Net FTJE impact |
| FTAX | Final Tax Return Balance | FINAL + FTJE |

## 8. Account Flags

| Flag | Display | Who Can Set |
|------|---------|-------------|
| Reviewed (preparer) | Green checkmark | Preparer |
| Issue | Red X | Preparer |
| Question | Yellow flag | Preparer |
| Reviewed (reviewer) | Purple R | Reviewer only |

## 9. Note Types

| Type | Who Creates | Who Can Resolve |
|------|-------------|-----------------|
| Preparer Note | Preparer | Preparer |
| Review Note | Reviewer | Reviewer only (preparer can respond/clear, not resolve) |
| Delivery Note | Reviewer | Reviewer (notes to signer for client deliverables) |

## 10. User Model and Roles

### First Launch — User Profile Setup

On first launch the app prompts the user to create a local profile:
- Full name (required)
- Initials (required; used on printed workpapers)
- Email (optional)

Profile is stored in a separate local app settings database (`atbw_settings.db` in the
app data folder — not inside any `.atbw` file). This profile stamps `performed_by` on all
activity log entries in every binder the user works on.

### Per-Binder Role Selection

Each time a binder is **created** or **opened**, the app presents a role dialog:
- "What is your role on this engagement?" → **Preparer** / **Reviewer**
- "Who is the reviewer?" → selected from a saved contacts list or typed as free text

Role selection is stored in the binder session only. It is not remembered between opens.
A person can be Preparer on one binder and Reviewer on another on the same machine.

Role determines which UI features are active for that session:
- **Preparer:** green/red/yellow flags, preparer notes, Clear button on review notes
- **Reviewer:** purple R flag, Resolve button, delivery notes, reviewer change tagging

### Admin Password

A firm-level admin password gates tax line template editing and the firm contacts list.
Any user who knows the admin password can access the admin panel. The password is set on
first launch and stored as a bcrypt hash in `atbw_settings.db`. It is never stored in a
`.atbw` file.

## 11. Tax Grouping

Tax line templates define the valid mapping targets per entity type (Balance Sheet and
P&L lines in display order). Stored in `atbw_settings.db`, not inside individual `.atbw`
files.

Templates are **admin-only**: a regular preparer or reviewer can view and use tax lines
for mapping but cannot add, edit, reorder, or deactivate lines without the admin password.

Admin panel functions (password-gated):
- Add / edit / reorder / deactivate tax lines per entity type and tax year
- Manage the firm contacts list (used for reviewer selection at binder open)
- Change admin password

## 12. Package Versioning

The app controls file names. Users do not manually name review packages.

```
YYYY Client Name TB Workup.atbw                                    ← native file
YYYY Client Name TB Workup - V01 - Ready for Review - 20260215-1435.atbr.xlsx
YYYY Client Name TB Workup - V02 - Reviewer Notes - 20260215-1610.atbr.xlsx
YYYY Client Name TB Workup - V03 - Cleared for Review - 20260216-0900.atbr.xlsx
YYYY Client Name TB Workup - FINAL.xlsx
YYYY Client Name TB Workup - FINAL.pdf
```

Status values: `Draft` | `In Prep` | `Ready for Review` | `Reviewer Notes` |
`Cleared for Review` | `Ready for Final Review` | `Final` | `Reopened`

## 13. Validation Gates

Before exporting a review package, the app checks:

- Trial balance is in balance (`SUM(pbc_balance) == 0`)
- All AJEs balance (`SUM(amount) == 0` per entry)
- All RJEs balance
- All accounts are mapped (no Unknown/Unmapped)
- No accounts assigned to placeholder groups
- Required sections are marked ready
- No unresolved import issues

Validation failures block export and display a diagnostics panel with links to problem records.

## 14. Review Controls

- Reviewer notes cannot be resolved by the preparer.
- Preparer can respond to a review note and mark it "Cleared."
- Only the reviewer can mark a note "Resolved."
- Finalized files are locked; reopening requires a logged reason.
- Every import/export is logged in the activity log.
- Package lineage is validated before import (version N+1 must reference version N).

## 15. Activity Log Events

```
created_workup | imported_tb | added_aje | changed_mapping
added_review_note | cleared_review_note | resolved_review_note
exported_package | imported_package | finalized | reopened_finalized
added_preparer_note | added_delivery_note
```

All log entries carry: timestamp, user, entity type, entity id, description.

## 16. Audit Trail in Excel Export

The activity log is written to a `xlSheetVeryHidden` sheet in all exported Excel files.
This ensures the audit trail is preserved as files are passed between team members and
reopened.

## 17. Out of Scope for MVP

Cloud sync, web app, multi-user simultaneous editing, tax software integration, full GL
workup, OCR, PDF editing, bank statement import, AI preparation, engagement management,
time tracking, client portal.

## 18. Design Principles

1. SQLite is the source of truth.
2. Excel is a review/export format, not a database.
3. Hidden metadata tabs support re-import; visible tabs are for humans.
4. Every record has a stable UUID; do not rely on row numbers or names.
5. Boring UI: tables, forms, validation panels, clear buttons.
6. No PDF editing; only generate from structured data.
7. Build incrementally; each milestone is small, working, and tested.
8. Reliability over cleverness.
