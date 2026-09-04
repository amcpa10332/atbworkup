# Future Improvements

Items to revisit after the core MVP is complete.

---

## UI / UX

- **Debounce grid refresh for large TBs** — `refresh()` is a full SQL query + tree rebuild. Sub-50ms on typical TBs, but worth adding a debounce if clients ever load thousands of lines.
- **Mapping workbench — drag and drop** — drag accounts from the left panel onto a tax line on the right instead of select-then-click.
- **Mapping workbench — general polish** — layout feels clunky; revisit spacing, panel sizing, and interaction flow once core features are stable.
- **Financial Statements view** — a separate read-only tab that renders a clean traditional report layout (no grid lines, no JE columns, just PBC / ADJ / FINAL / FTAX with proper indentation and section totals). Distinct from the working Trial Balance tab.
- **Trial Balance expand/collapse all** — toolbar buttons to expand or collapse all section groups in the trial balance grid at once.

---

## Performance

*(none yet)*

---

## Data / Export

- **Preparer checklist before export** — a structured pre-export checklist (separate from the validation engine) where the preparer can tick off steps like "reconciled bank statements", "reviewed depreciation schedule", "confirmed officer comp", etc. Checklist is saved to the binder and included on the cover sheet of the review package.
- **Collapsible row groups in review workbook** — explore Excel row grouping (`ws.row_dimensions[r].outline_level`) so sections in the Balance Sheet, Income Statement, and Tax Grouping tabs can be collapsed/expanded natively in Excel without macros.

---

## Nice-to-Have

- **Reopen closed notes** — allow a reviewer or preparer to reopen a note that was marked Cleared, with an optional comment explaining why.
- **Note threading** — allow replies within a note so preparer/reviewer can have a back-and-forth without creating separate linked notes.
