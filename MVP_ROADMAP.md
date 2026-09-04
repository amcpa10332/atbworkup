# MVP_ROADMAP.md — Trial Balance Workup Tool

Each milestone is small, independently shippable, and has a clear "done" condition.
Do not start the next milestone until the current one passes all its tests.

---

## M1 — Native File + Job Metadata

**Goal:** The app can create, save, and reopen a `.atbw` file.

**Deliverables:**
- Start screen with three buttons: Create New Workup / Open Existing Workup / Import Review Package
- "Create New Workup" dialog: client name, entity name, tax year, entity type, prepared by,
  reviewer (optional), workpaper folder, accounting system
- Creates `YYYY Client Name TB Workup.atbw` (SQLite) in the chosen folder
- Full initial schema applied on create
- Reopening loads job metadata and shows it in a read-only panel
- Activity log entry on create and on open

**Done when:** App creates a file, closes, reopens, displays metadata correctly.
Tests pass for schema creation, metadata save/load, activity log insert.

---

## M2 — Excel Trial Balance Import Wizard

**Goal:** The app can import a real-world Excel trial balance into the `accounts` table.

**Deliverables:**
- File picker (xlsx/xls)
- Sheet selector if workbook has multiple sheets
- Preview grid (first 30 rows, scrollable)
- Column selector: header row, account number, account name, balance column(s)
- Auto-detection of header row (heuristic: first row where name col is a string and
  balance col is blank or header text)
- Support for single-column and two-column (Dr/Cr) layouts
- Parenthetical negative number parsing: `(1,234.56)` → `-1234.56`
- Running debit/credit totals shown in preview
- Confirmation step before writing to database
- On confirm: accounts written to `accounts` table, `is_mapped = 0`
- Activity log: `imported_tb`

**Done when:** Can import 3 different real-world TB formats (single col, two col, mixed
formatting) and round-trip balances match source to the cent.

---

## M3 — Financial Statement Grid (Display)

**Goal:** Imported accounts are displayed as a financial statement grid.

**Deliverables:**
- Grid view with accounts grouped by financial statement (Balance Sheet / P&L)
- Columns: Account Number, Account Name, PBC, AJE, ADJ, RJE, FINAL, FTJE, FTAX
- Computed columns (ADJ, FINAL, FTAX) calculated in real time from database
- Section subtotals and grand totals
- Checkbox column on the left for multi-select
- Flag icon column: green/red/yellow; click to toggle
- Read-only at this milestone (no editing yet)
- Unmapped accounts shown at the bottom in an "Unmapped" group

**Done when:** Grid renders all accounts correctly with accurate computed totals.

---

## M4 — Account Mapping

**Goal:** Preparers can map accounts to tax lines and workpaper sections.

**Deliverables:**
- Tax line templates for each entity type (editable YAML or SQLite-backed config)
  - 1120-S, 1065, 1120, Schedule C, 990, 1041
  - Each has Balance Sheet and P&L lines in display order
- Mapping utility dialog: list of tax lines for the entity type, searchable
- Single-account and bulk-account mapping (via checkbox multi-select)
- Section assignment in same dialog
- Mapping written to `mappings` table
- Grid re-renders accounts under their mapped tax line after save
- Unmapped accounts counter shown prominently
- Activity log: `changed_mapping` per account

**Done when:** Can map all accounts in a sample TB; grid shows correct groupings; remapping
updates grouping immediately.

---

## M5 — Journal Entries

**Goal:** Preparers can create and edit AJEs, RJEs, and FTJEs; computed columns update live.

**Deliverables:**
- JE panel (collapsible, dockable) with full debit/credit line editor
- Entry types: AJE, RJE, FTJE
- Auto-numbered entry codes: `AJE-001`, `AJE-002`, etc.
- Balance indicator on each entry (red if unbalanced)
- Grid `+` button in each JE column cell → creates a shell entry for that account,
  opens the JE panel with that line pre-filled
- Shell entries are saved but flagged `status = Shell` until balanced
- Computed columns (ADJ, FINAL, FTAX) update in real time as entries change
- Activity log: `added_aje` on create, `changed_aje` on edit

**Done when:** Can create a balanced AJE via grid and via JE panel; ADJ/FINAL/FTAX update
immediately; unbalanced entries are flagged.

---

## M6 — Notes and Flags

**Goal:** Preparers can create notes linked to accounts and JEs; notes are highly visible.

**Deliverables:**
- Notes panel (always visible, dockable)
- Right-click account or JE row → "Add Note" → type: preparer
- Note body text editor
- Notes list in panel: sorted by creation date, filtered by Open/All
- Clicking a note in the panel navigates to the linked account or JE row in the grid
- "Open Notes" badge count on main window title bar
- Second-window support: user can detach notes panel into a separate window
  (so they can view financials and notes side by side)
- Account flag column: green checkmark, red X, yellow flag (click to cycle)
- Activity log: `added_preparer_note`

**Done when:** Can create a note, see it in the panel, click it to navigate, open the
notes panel in a second window.

---

## M7 — Validation and Export Review Package

**Goal:** App validates the workup and exports a `V01` `.atbr.xlsx` review package.

**Deliverables:**
- "Ready for Review" button in toolbar
- Optional preparer checklist dialog (configurable list of checkboxes)
- Validation engine checks (PROJECT_SPEC §10):
  - TB in balance
  - All AJEs balance
  - All accounts mapped
  - No Unknown/placeholder group assignments
  - Required sections ready
- Diagnostics panel shows failures with links to problem records
- On all-pass: generates `.atbr.xlsx` with visible tabs + hidden `__` tabs
- All `__` tabs are `xlSheetVeryHidden`
- Activity log written to `__activity_log` tab
- `__manifest` tab with checksum
- Package record written to `packages` table
- Status → `Ready for Review`
- File saved to workpaper folder with auto-generated name

**Done when:** Export produces a valid `.atbr.xlsx`; hidden tabs present and veryHidden;
checksum verifiable by re-reading the file.

---

## M8 — Import Review Package (Re-import)

**Goal:** App can re-import a `.atbr.xlsx` and validate its lineage and integrity.

**Deliverables:**
- "Import Review Package" on start screen and File menu
- Manifest validation: version, job_id, lineage, checksum
- Clear error messages for each validation failure
- On valid: show import summary (changes, notes, mapping changes)
- Write all reviewer data to `.atbw` with `originated_by = reviewer` tags
- Conflict detection: if local changes conflict with incoming reviewer changes,
  show merge/accept screen (side by side, accept per item)
- Activity log: `imported_package`

**Done when:** Can export V01, manually edit hidden tabs to simulate reviewer response,
re-import, and see reviewer notes and changes in the app.

---

## M9 — Review Notes and Reviewer UI

**Goal:** Reviewer-specific features: review notes, delivery notes, purple R, resolve.

**Deliverables:**
- When a review package (not `.atbw`) is open, reviewer UI mode activates
- Purple R flag on accounts (reviewer only)
- "Add Review Note" and "Add Delivery Note" options
- Resolve button on review notes (reviewer only; hidden/disabled for preparers)
- Preparer "Clear" button on review notes
- Notes panel shows type (preparer/review/delivery) with color coding
- Reviewer changes summary panel (all changes tagged `reviewer`)
- Reviewer export: `V02` or next version with all reviewer data

**Done when:** Reviewer can add notes, mark accounts, and export a response package that
the preparer can re-import; note resolution rules are enforced.

---

## M10 — Versioned Exchange Workflow

**Goal:** Full V01→V02→V03→... cycle works end to end.

**Deliverables:**
- Version counter increments correctly on each export
- Prior_package_id chain is maintained
- Lineage validation catches out-of-order imports
- Status transitions follow the state machine in REVIEW_WORKFLOW.md
- File names are always auto-generated (no user override)
- Prior Year Comparison screen (basic): import PY `.atbw` or manual entry;
  show FINAL and FTAX side by side with current year

**Done when:** Can run a complete V01 → V02 → V03 cycle and all records are correct in
the final `.atbw`.

---

## M11 — Finalization

**Goal:** App generates locked FINAL.xlsx and FINAL.pdf.

**Deliverables:**
- "Finalize" button (reviewer or signer)
- Generates `FINAL.xlsx` with all tabs including `__activity_log` (veryHidden)
- Generates `FINAL.pdf` (cover + financials + JEs; no audit log)
- `job.status` → `Final`; `job.finalized_at` and `job.finalized_by` set
- Reopening a finalized file requires a reason dialog; logs `reopened_finalized`
- Activity log: `finalized`

**Done when:** FINAL files generated; file locked; reopen with reason works.

---

## M12 — Roll-Forward

**Goal:** User can create a new workup by rolling forward from a prior-year `.atbw`.

**Deliverables:**
- "Roll Forward from Prior Year" option on Create New Workup dialog
- Imports from prior-year `.atbw`:
  - Account mappings
  - Tax groups
  - Workpaper sections
  - Recurring AJE templates (marked as templates, not active entries)
  - Prior-year FINAL and FTAX balances → `prior_year_balances` table
- Does NOT bring forward review notes as active
- Prior-year review notes visible in a read-only "Prior Year Notes" panel
- Activity log: `rolled_forward`

**Done when:** Can create a new workup from a prior year file, and mappings, sections, and
PY balances are correctly populated.

---

## M13 — Mapping Templates and Diagnostics

**Goal:** Reusable mapping templates; expanded diagnostic rules.

**Deliverables:**
- Save mapping set as a named template (per entity type)
- Apply template to a new workup during or after import
- Expanded diagnostics (PROJECT_SPEC §11):
  - Negative cash, negative debt
  - Ask My Accountant / Uncategorized Expense accounts
  - Large expense with fixed-asset keywords
  - Large PY variance
- Diagnostics panel accessible any time (not just at export)

**Done when:** Template save/load works; new diagnostics fire correctly on sample data.

---

## Post-MVP (Do Not Build in MVP)

- Cloud sync
- Multi-user simultaneous editing
- Tax software direct integration
- AI-assisted preparation
- Client portal
- Time tracking
- OCR / document reading
- Bank statement import
- Complex permission / role management
- Later diagnostics (officer comp, distributions, payroll tie-out, state items)

---

## Dependency Graph

```
M1 → M2 → M3 → M4 → M5 → M6 → M7 → M8 → M9 → M10 → M11
                                                    ↓
                                                   M12
                                                    ↓
                                                   M13
```

Each milestone depends on all prior milestones. No skipping.
