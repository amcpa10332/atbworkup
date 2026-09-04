# DATA_MODEL.md — Trial Balance Workup Tool

## Two Databases

| File | Location | Contents |
|------|----------|----------|
| `YYYY Client Name TB Workup.atbw` | User's workpaper folder | All binder data (tables below) |
| `atbw_settings.db` | OS app-data folder (`%APPDATA%\ATBWorkup\`) | User profile, admin settings, tax line templates, contacts |

Tables below marked **[binder]** live in the `.atbw` file.
Tables marked **[settings]** live in `atbw_settings.db`.

---

## Settings Database Tables

### Table: `user_profile` [settings]

One row. Created on first launch.

| Column | Type | Notes |
|--------|------|-------|
| profile_id | TEXT PK | UUID |
| full_name | TEXT NOT NULL | |
| initials | TEXT NOT NULL | |
| email | TEXT | optional |
| created_at | TEXT NOT NULL | |

### Table: `admin_settings` [settings]

One row. Created on first launch.

| Column | Type | Notes |
|--------|------|-------|
| settings_id | TEXT PK | UUID |
| password_hash | TEXT NOT NULL | bcrypt hash; never plaintext |
| updated_at | TEXT NOT NULL | |

### Table: `contacts` [settings]

Firm contact list for reviewer selection at binder open.

| Column | Type | Notes |
|--------|------|-------|
| contact_id | TEXT PK | UUID |
| full_name | TEXT NOT NULL | |
| initials | TEXT | |
| email | TEXT | |
| is_active | INTEGER NOT NULL DEFAULT 1 | |

---

## Binder Tables

All tables live inside the `.atbw` SQLite file.
Primary keys are UUIDs (TEXT, stored as hex strings without dashes).
Foreign keys are enforced (`PRAGMA foreign_keys = ON` on every connection).
All timestamps are ISO-8601 UTC strings: `2026-02-15T14:35:00Z`.

---

## Table: `job`

Single-row table. One row per `.atbw` file.

| Column | Type | Notes |
|--------|------|-------|
| job_id | TEXT PK | UUID |
| client_name | TEXT NOT NULL | |
| entity_name | TEXT NOT NULL | |
| tax_year | INTEGER NOT NULL | e.g. 2025 |
| entity_type | TEXT NOT NULL | `1120S`, `1065`, `1120`, `ScheduleC`, `990`, `1041` |
| prepared_by | TEXT NOT NULL | |
| reviewer | TEXT | nullable |
| workpaper_folder | TEXT | local path |
| accounting_system | TEXT | e.g. `QuickBooks`, `Xero` |
| is_rollforward | INTEGER NOT NULL DEFAULT 0 | boolean |
| prior_year_job_id | TEXT | FK → prior-year job_id (optional) |
| status | TEXT NOT NULL DEFAULT 'Draft' | see status list in PROJECT_SPEC |
| schema_version | TEXT NOT NULL | e.g. `1.0` |
| app_version | TEXT NOT NULL | e.g. `0.1.0` |
| created_at | TEXT NOT NULL | |
| updated_at | TEXT NOT NULL | |
| finalized_at | TEXT | |
| finalized_by | TEXT | |

---

## Table: `accounts`

One row per account from the imported trial balance.

| Column | Type | Notes |
|--------|------|-------|
| account_id | TEXT PK | UUID |
| job_id | TEXT NOT NULL FK → job | |
| account_number | TEXT | from source TB |
| account_name | TEXT NOT NULL | |
| account_type | TEXT NOT NULL | `Asset`, `Liability`, `Equity`, `Revenue`, `Expense`, `OtherIncome`, `OtherExpense` |
| pbc_balance | REAL NOT NULL DEFAULT 0 | Provided by Client balance |
| normal_balance | TEXT NOT NULL | `Debit` or `Credit` |
| source_row | INTEGER | row number in source Excel |
| is_mapped | INTEGER NOT NULL DEFAULT 0 | boolean |
| flag | TEXT | `reviewed`, `issue`, `question`, `reviewer_reviewed`, NULL |
| sort_order | INTEGER | display order within financial statement |
| created_at | TEXT NOT NULL | |
| updated_at | TEXT NOT NULL | |

---

## Table: `tax_lines` [settings]

Configurable list of tax reporting lines per entity type.
Lives in `atbw_settings.db`. Editable only via the admin-password-gated admin panel.

| Column | Type | Notes |
|--------|------|-------|
| tax_line_id | TEXT PK | UUID |
| entity_type | TEXT NOT NULL | |
| financial_statement | TEXT NOT NULL | `BalanceSheet`, `ProfitAndLoss` |
| line_code | TEXT NOT NULL | e.g. `BS-001`, `PL-042` |
| line_name | TEXT NOT NULL | e.g. `Cash and Cash Equivalents` |
| sort_order | INTEGER NOT NULL | |
| is_active | INTEGER NOT NULL DEFAULT 1 | |
| tax_year | INTEGER | NULL = all years |

---

## Table: `mappings`

Maps each account to a tax line and workpaper section.

| Column | Type | Notes |
|--------|------|-------|
| mapping_id | TEXT PK | UUID |
| account_id | TEXT NOT NULL FK → accounts | |
| job_id | TEXT NOT NULL FK → job | |
| tax_line_id | TEXT FK → tax_lines | nullable until mapped |
| section_id | TEXT FK → sections | nullable |
| mapped_by | TEXT NOT NULL | `preparer` or `reviewer` |
| mapped_at | TEXT NOT NULL | |
| notes | TEXT | |

One active mapping per account. Historical mapping changes are captured in `activity_log`.

---

## Table: `sections`

Workpaper sections (e.g., "Cash," "AR," "Revenue").

| Column | Type | Notes |
|--------|------|-------|
| section_id | TEXT PK | UUID |
| job_id | TEXT NOT NULL FK → job | |
| section_name | TEXT NOT NULL | |
| entity_type | TEXT NOT NULL | |
| sort_order | INTEGER NOT NULL | |
| status | TEXT NOT NULL DEFAULT 'Open' | `Open`, `Ready`, `Reviewed` |
| created_at | TEXT NOT NULL | |
| updated_at | TEXT NOT NULL | |

---

## Table: `journal_entries`

Header record for each AJE, RJE, or FTJE.

| Column | Type | Notes |
|--------|------|-------|
| aje_id | TEXT PK | UUID |
| job_id | TEXT NOT NULL FK → job | |
| entry_type | TEXT NOT NULL | `AJE`, `RJE`, `FTJE` |
| entry_number | TEXT NOT NULL | e.g. `AJE-001` |
| description | TEXT NOT NULL | |
| originated_by | TEXT NOT NULL | `preparer` or `reviewer` |
| originated_at | TEXT NOT NULL | |
| is_balanced | INTEGER NOT NULL DEFAULT 0 | computed flag |
| status | TEXT NOT NULL DEFAULT 'Open' | `Open`, `Shell`, `Finalized` |
| package_version | INTEGER | version when first created (NULL = native) |

---

## Table: `journal_entry_lines`

Detail lines for each journal entry.

| Column | Type | Notes |
|--------|------|-------|
| line_id | TEXT PK | UUID |
| aje_id | TEXT NOT NULL FK → journal_entries | |
| account_id | TEXT NOT NULL FK → accounts | |
| amount | REAL NOT NULL | DR = positive, CR = negative |
| memo | TEXT | |
| sort_order | INTEGER NOT NULL | |

Constraint: for a balanced entry, `SUM(amount) = 0`.
Shell entries (created from the + button on the grid) may be unbalanced until completed.

---

## Table: `notes`

All preparer notes, review notes, and delivery notes.

| Column | Type | Notes |
|--------|------|-------|
| note_id | TEXT PK | UUID |
| job_id | TEXT NOT NULL FK → job | |
| note_type | TEXT NOT NULL | `preparer`, `review`, `delivery` |
| linked_to_type | TEXT | `account`, `aje`, `general` |
| linked_to_id | TEXT | FK to accounts.account_id or journal_entries.aje_id; NULL if general |
| body | TEXT NOT NULL | |
| created_by | TEXT NOT NULL | |
| created_at | TEXT NOT NULL | |
| status | TEXT NOT NULL DEFAULT 'Open' | `Open`, `Cleared`, `Resolved` |
| cleared_by | TEXT | |
| cleared_at | TEXT | |
| resolved_by | TEXT | reviewer only |
| resolved_at | TEXT | |
| package_version | INTEGER | version when created |

---

## Table: `signoffs`

Records preparer and reviewer sign-offs.

| Column | Type | Notes |
|--------|------|-------|
| signoff_id | TEXT PK | UUID |
| job_id | TEXT NOT NULL FK → job | |
| signoff_type | TEXT NOT NULL | `preparer_ready`, `reviewer_complete`, `final` |
| signed_by | TEXT NOT NULL | |
| signed_at | TEXT NOT NULL | |
| package_version | INTEGER | |
| notes | TEXT | |

---

## Table: `packages`

One row per exported review package.

| Column | Type | Notes |
|--------|------|-------|
| package_id | TEXT PK | UUID |
| job_id | TEXT NOT NULL FK → job | |
| version_number | INTEGER NOT NULL | 1, 2, 3 … |
| package_type | TEXT NOT NULL | `review`, `response`, `final` |
| status_label | TEXT NOT NULL | e.g. `Ready for Review` |
| file_name | TEXT NOT NULL | controlled name, no manual override |
| file_path | TEXT | local path at time of export |
| exported_by | TEXT NOT NULL | |
| exported_at | TEXT NOT NULL | |
| imported_at | TEXT | when re-imported |
| imported_by | TEXT | |
| prior_package_id | TEXT FK → packages | lineage chain |
| checksum | TEXT | SHA-256 of exported file |

---

## Table: `activity_log`

Immutable append-only event log.

| Column | Type | Notes |
|--------|------|-------|
| activity_id | TEXT PK | UUID |
| job_id | TEXT NOT NULL FK → job | |
| event_type | TEXT NOT NULL | see event list in PROJECT_SPEC |
| entity_type | TEXT | `account`, `aje`, `note`, `package`, etc. |
| entity_id | TEXT | ID of the affected record |
| description | TEXT NOT NULL | human-readable |
| performed_by | TEXT NOT NULL | |
| performed_at | TEXT NOT NULL | |
| package_version | INTEGER | version active when event occurred |
| metadata_json | TEXT | optional extra context (JSON blob) |

No UPDATE or DELETE on this table. Rows are inserted only.

---

## Table: `prior_year_balances`

Stores PY balances for comparison, either from a roll-forward or manual entry.

| Column | Type | Notes |
|--------|------|-------|
| py_balance_id | TEXT PK | UUID |
| job_id | TEXT NOT NULL FK → job | |
| account_id | TEXT FK → accounts | NULL if entered at group/section level |
| section_id | TEXT FK → sections | NULL if account-level |
| tax_line_id | TEXT FK → tax_lines | |
| py_final_balance | REAL | FINAL column from prior year |
| py_ftax_balance | REAL | FTAX column from prior year |
| source | TEXT NOT NULL | `rollforward`, `manual` |
| entered_at | TEXT NOT NULL | |

---

## Sign Convention

All monetary values use a single signed number: **debits positive, credits negative**.
This is consistent across `accounts.pbc_balance`, `journal_entry_lines.amount`,
and all computed financial statement columns.

## Computed Values (not stored)

These are calculated at query time, never persisted:

- `ADJ = PBC + SUM(amount WHERE entry_type = 'AJE' for account)`
- `FINAL = ADJ + SUM(amount WHERE entry_type = 'RJE' for account)`
- `FTAX = FINAL + SUM(amount WHERE entry_type = 'FTJE' for account)`

---

## App Settings Database (separate from `.atbw`)

A separate SQLite file — `atbw_settings.db` — lives in the user's app data folder
(`%APPDATA%\ATBWorkup\`). It is not a binder file. It stores:

**`user_profile` table** (one row)

| Column | Type | Notes |
|--------|------|-------|
| full_name | TEXT NOT NULL | |
| initials | TEXT NOT NULL | |
| email | TEXT | |
| created_at | TEXT NOT NULL | |

**`firm_contacts` table** (one row per known reviewer/signer)

| Column | Type | Notes |
|--------|------|-------|
| contact_id | TEXT PK | UUID |
| full_name | TEXT NOT NULL | |
| initials | TEXT | |
| email | TEXT | |

**`admin_settings` table** (one row)

| Column | Type | Notes |
|--------|------|-------|
| password_hash | TEXT NOT NULL | bcrypt hash of admin password |
| set_at | TEXT NOT NULL | |

**`tax_lines` template data** lives in the app settings database, not in individual
`.atbw` files. When a binder is opened, it reads templates from `atbw_settings.db`.
Each `.atbw` file stores only the mapping records (which tax_line_id was chosen), not
the full template definition.

---

## Schema Versioning

The `job.schema_version` column tracks the schema version used when the file was created.
A migration runner checks this on open and applies forward migrations as needed.
Migration scripts live in `db/migrations/`.
