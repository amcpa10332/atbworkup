# REVIEW_WORKFLOW.md — Trial Balance Workup Tool

This document defines the full prep/review exchange cycle: who does what, in what order,
what is blocked, and how the app enforces each control.

---

## Roles

| Role | Description |
|------|-------------|
| Preparer | Creates the workup, maps accounts, makes AJEs, clears notes |
| Reviewer | Reviews the package, adds review notes, proposes changes |
| Signer | Receives delivery notes; finalizes (may be same person as reviewer) |
| Admin | Manages tax line templates and firm-level settings (password-protected) |

**User profile (first launch):** On first launch the app prompts the user to set up a
profile: full name, initials, email (optional). Stored in local app settings (not in any
`.atbw` file). This profile stamps `performed_by` on all activity log entries.

**Per-binder role selection:** Each time a binder is created or opened, the app presents
a role dialog:
- "What is your role on this engagement?" → Preparer / Reviewer
- "Who is the reviewer?" → selected from a saved contact list or typed in free text

Role selection is stored in the binder session only; it is not a global login. A person
can be Preparer on one binder and Reviewer on another. Role-specific UI features (purple R
flag, Resolve button, delivery notes) are shown or hidden based on the selected role for
that binder.

---

## State Machine

```
Draft
  │  (preparer imports TB, maps accounts, creates AJEs)
  ▼
In Prep
  │  (preparer clicks "Ready for Review"; validation passes)
  ▼
Ready for Review  ──► V01 .atbr.xlsx exported
  │  (reviewer opens V01)
  ▼
[Reviewer working...]
  │  (reviewer exports response)
  ▼
Reviewer Notes  ──► V02 .atbr.xlsx exported
  │  (preparer imports V02)
  ▼
[Preparer clearing notes...]
  │  (preparer exports cleared package)
  ▼
Cleared for Review  ──► V03 .atbr.xlsx exported
  │  (reviewer reviews clearances)
  ▼
  ├── More notes? → Reviewer Notes (V04...) → repeat
  └── Approved? →
Ready for Final Review
  │  (final sign-off)
  ▼
Final
  │  (FINAL.xlsx + FINAL.pdf generated; file locked)
  ▼
[Locked]
  │  (if reopened: reason required → logged → status = Reopened)
  ▼
Reopened
```

---

## Step-by-Step Procedures

### Step 1 — Preparer: Create Workup

1. Open app → "Create New Workup."
2. Enter job metadata (client, entity, tax year, entity type, preparer, reviewer, folder).
3. App creates `YYYY Client Name TB Workup.atbw`.
4. Activity log: `created_workup`.

### Step 2 — Preparer: Import Trial Balance

1. Click "Import Trial Balance."
2. Import wizard: select file → preview → choose columns → confirm.
3. Accounts written to `accounts` with `is_mapped = 0`.
4. Activity log: `imported_tb`.
5. Status → `In Prep`.

### Step 3 — Preparer: Map Accounts

1. Financial statement grid shows all unmapped accounts highlighted.
2. Preparer selects one or more accounts (checkbox column) → "Map Selected."
3. Mapping utility shows tax line list for the entity type.
4. Preparer selects tax line + workpaper section → Save.
5. Activity log: `changed_mapping` for each account.

### Step 4 — Preparer: Create Journal Entries

Two entry points:
- **Grid quick-add:** click `+` in any AJE/RJE/FTJE column cell → creates a shell entry
  for that account. Shell entries appear in the JE utility as incomplete.
- **JE utility panel:** full debit/credit line editor. Can be open alongside the grid.

All changes are live; computed columns (ADJ, FINAL, FTAX) update in real time.

### Step 5 — Preparer: Add Notes and Flags

- Right-click account or JE → "Add Note" → choose type (preparer) → enter body.
- Click flag icon on account row → set flag (green/red/yellow).
- Outstanding notes are shown in a Notes panel (dockable, always visible).
- Clicking a note in the panel navigates to the linked account or JE.

### Step 6 — Preparer: Export Review Package

1. Click "Ready for Review."
2. Optional: preparer checklist popup (interactive checkbox list).
3. App runs validation checks (see PROJECT_SPEC §10). Any failure shows diagnostics panel.
4. All checks pass → app generates `V01` `.atbr.xlsx` in the workpaper folder.
5. App updates `packages` table and `activity_log`.
6. Status → `Ready for Review`.

### Step 7 — Reviewer: Open Review Package

1. Open app → "Import Review Package" → select `.atbr.xlsx`.
2. App validates manifest, job_id, version lineage, and checksum.
3. If valid: reviewer interface loads. All preparer data is visible.
4. Reviewer-specific UI elements are enabled: purple R flag, "Resolve Note," delivery notes.

### Step 8 — Reviewer: Review

Reviewer can:
- View and edit account mappings (changes tagged `reviewer`).
- View and edit AJEs; create new ones (tagged `reviewer`).
- Add review notes linked to accounts, AJEs, or general.
- Add delivery notes (for signer/client deliverable items).
- Mark accounts with purple R (reviewer-reviewed flag).
- Mark sections as `Reviewed`.
- View all preparer notes (cannot resolve them).

All reviewer-originated changes are tagged `originated_by = reviewer`.

### Step 9 — Reviewer: Export Response Package

1. Reviewer clicks "Export Reviewer Response."
2. App generates `V02` `.atbr.xlsx`.
3. All reviewer changes and notes are written to hidden tabs.
4. Activity log: `exported_package`.
5. Status → `Reviewer Notes`.

### Step 10 — Preparer: Import Reviewer Notes

1. Open app → "Import Review Package" → select `V02` file.
2. App validates: manifest, job_id, version = `current + 1`, prior_package_id matches.
3. If valid, shows import summary:
   - Reviewer notes added: N
   - Reviewer mapping changes: N
   - Reviewer AJEs: N
   - Conflicts (if any): → merge screen
4. On accept: all reviewer data is written to `.atbw`.
5. Activity log: `imported_package`.

### Step 11 — Preparer: Clear Notes

1. Notes panel shows all open review notes.
2. Preparer can respond to a note (adds a response body) and click "Clear."
3. Note status → `Cleared`. Reviewer must still accept.
4. Preparer cannot click "Resolve" — that button is hidden/disabled for preparers.
5. Once all notes are cleared → preparer exports `V03` (`Cleared for Review`).

### Step 12 — Reviewer: Accept or Reject Clearances

1. Reviewer opens `V03`.
2. Sees all notes marked `Cleared` with preparer responses.
3. Reviewer can: "Resolve" (close note) or re-open (add another review note).
4. If satisfied → reviewer signals final sign-off.
5. Status → `Ready for Final Review`.

### Step 13 — Finalization

1. Reviewer (or designated signer) clicks "Finalize."
2. App generates:
   - `YYYY Client Name TB Workup - FINAL.xlsx`
   - `YYYY Client Name TB Workup - FINAL.pdf`
3. `.atbw` file is locked (read-only flag in `job` table).
4. Activity log: `finalized`.
5. Status → `Final`.

---

## Reopening a Finalized File

1. User opens a finalized `.atbw`.
2. App detects `status = Final` and shows a dialog: "This file is finalized. Enter a
   reason to reopen it."
3. Reason is required (non-blank).
4. Activity log: `reopened_finalized` with reason.
5. Status → `Reopened`.
6. New exports will use the next version number.
7. Existing `FINAL.xlsx` and `FINAL.pdf` are NOT overwritten automatically.

---

## Note Resolution Rules (Summary)

| Action | Preparer | Reviewer |
|--------|----------|----------|
| Create review note | No | Yes |
| Respond to review note | Yes | Yes |
| Mark review note "Cleared" | Yes | Yes |
| Mark review note "Resolved" | No | Yes |
| Create preparer note | Yes | No |
| Resolve preparer note | Yes | No |
| Create delivery note | No | Yes |
| Resolve delivery note | No | Yes |

---

## Package Lineage Validation

Before importing any `.atbr.xlsx`, the app verifies:

```
incoming.version_number == max(packages.version_number) + 1
incoming.prior_package_id == packages[max version].package_id
incoming.job_id == job.job_id
incoming.checksum == recomputed checksum of hidden tabs
```

Any mismatch → import blocked, descriptive error shown. No partial imports.

---

## Reviewer Change Tagging

Every change a reviewer makes inside a review package is tagged:
- `mappings.mapped_by = 'reviewer'`
- `journal_entries.originated_by = 'reviewer'`
- `notes.created_by = reviewer name`

On re-import, the app shows a "Reviewer Changes" summary panel so the preparer and signer
can see exactly what was changed during review — to identify training gaps and support
accountability.
