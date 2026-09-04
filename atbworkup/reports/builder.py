"""
Report builder — computes Balance Sheet and P&L data from the binder DB.

Sign convention (internal DB): DR = positive, CR = negative.
Display convention: Liabilities, Equity, and Revenue are negated before
display so all amounts appear positive.

Column progression per account:
  UNADJ  = pbc_balance
  AJE    = sum of AJE-type entry lines
  ADJ    = UNADJ + AJE
  RJE    = sum of RJE-type entry lines
  FINAL  = ADJ + RJE        ← primary "book final" column
  FTJE   = sum of FTJE-type entry lines
  FTAX   = FINAL + FTJE     ← tax-basis column
"""
from __future__ import annotations

from dataclasses import dataclass, field

from atbworkup.data.tax_line_categories import (
    ASSET_CATEGORIES, LIABILITY_CATEGORIES, CATEGORY_EQUITY, CATEGORY_REVENUE,
    CATEGORY_SCHEDULE_K,
)

# Categories whose raw DR/CR balance gets negated for display, decided ONCE
# per tax line (via its stored category) rather than per account's own
# normal_balance. This matters because a section legitimately mixes credit-
# normal core accounts (Retained Earnings) with debit-normal CONTRA accounts
# that share the same category (Owner Distributions, Draws — debit-normal,
# but still "equity", meant to REDUCE it). Flipping per-account normal_balance
# instead of per-category leaves contra accounts un-flipped, so they display
# as a positive addition instead of a negative reduction — the section total
# stops tying to its true raw value and the whole statement goes out of
# balance. (Root cause of the long-standing "in-app report out of balance"
# reports — the Excel exporter uses this same category-based rule and always
# tied out correctly.)
#
# Schedule K is in this set too, but for a different reason: Revenue/
# Liability/Equity are flipped because ALL their lines share one polarity, so
# a blanket negation is "the same subtraction, done once." Schedule K is the
# opposite case — it's explicitly MIXED_SIGN (income-type and deduction-type
# lines share the category) and there's no further formula that subtracts it
# from anything else (unlike COGS/Deductions, which get subtracted via Gross
# Profit/Operating Income) — its section total is added straight into net
# income. So each line's raw value already IS its signed contribution to net
# income (via net_income = -sum(raw)); negating it for display is exactly
# "show what this line does to net income," not a structural subtraction.
# Without this, an income-type line like Interest Income displays as a
# negative/credit balance even though it increases net income, which reads
# backwards next to Revenue (which gets the same treatment) directly above it.
_FLIP_CATEGORIES = LIABILITY_CATEGORIES | {CATEGORY_EQUITY, CATEGORY_REVENUE, CATEGORY_SCHEDULE_K}


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class ReportLine:
    account_id:     str
    account_number: str
    account_name:   str
    account_type:   str       # "Asset" | "Liability" | "Equity" | "Revenue" | "Expense"
    normal_balance: str       # "Debit" | "Credit"
    pbc_balance:    float     # UNADJ
    aje_total:      float     # AJE entries only
    rje_total:      float     # RJE entries only
    ftje_total:     float     # FTJE entries only
    category:       str   = ""  # stored tax-line category — see _FLIP_CATEGORIES
    has_open_notes: bool  = False
    flag:           str   = ""  # preparer flag: "" | "question" | "reviewed" | "issue"
    py_final:       float = 0.0
    py_ftax:        float = 0.0

    # ── Computed column values ─────────────────────────────────────────────
    @property
    def adj_balance(self) -> float:
        return self.pbc_balance + self.aje_total

    @property
    def final_balance(self) -> float:
        return self.adj_balance + self.rje_total

    @property
    def ftax_balance(self) -> float:
        return self.final_balance + self.ftje_total

    # backward-compat alias
    @property
    def adjusted_balance(self) -> float:
        return self.final_balance

    # ── Display helpers (sign-flip decided per tax-line category) ──────────
    def _d(self, v: float) -> float:
        if self.category:
            return -v if self.category in _FLIP_CATEGORIES else v
        # Legacy/un-migrated line with no stored category — fall back to the
        # old per-account normal_balance flip (wrong for contra accounts that
        # share a category with credit-normal peers, but no worse than before).
        return -v if self.normal_balance == "Credit" else v

    @property
    def display_pbc(self) -> float:
        return self._d(self.pbc_balance)

    @property
    def display_aje(self) -> float:
        return self._d(self.aje_total)

    @property
    def display_adj(self) -> float:
        return self._d(self.adj_balance)

    @property
    def display_rje(self) -> float:
        return self._d(self.rje_total)

    @property
    def display_final(self) -> float:
        return self._d(self.final_balance)

    @property
    def display_ftje(self) -> float:
        return self._d(self.ftje_total)

    @property
    def display_ftax(self) -> float:
        return self._d(self.ftax_balance)

    # backward-compat alias used by pdf_report
    @property
    def display_balance(self) -> float:
        return self.display_final

    @property
    def display_py_final(self) -> float:
        return self._d(self.py_final)

    @property
    def display_py_ftax(self) -> float:
        return self._d(self.py_ftax)


@dataclass
class ReportSection:
    name:       str
    sort_order: int
    lines:      list[ReportLine] = field(default_factory=list)

    # ── Display subtotals ──────────────────────────────────────────────────
    @property
    def subtotal_pbc(self) -> float:
        return sum(ln.display_pbc   for ln in self.lines)

    @property
    def subtotal_aje(self) -> float:
        return sum(ln.display_aje   for ln in self.lines)

    @property
    def subtotal_adj(self) -> float:
        return sum(ln.display_adj   for ln in self.lines)

    @property
    def subtotal_rje(self) -> float:
        return sum(ln.display_rje   for ln in self.lines)

    @property
    def subtotal(self) -> float:
        return sum(ln.display_final for ln in self.lines)

    @property
    def subtotal_ftje(self) -> float:
        return sum(ln.display_ftje  for ln in self.lines)

    @property
    def subtotal_ftax(self) -> float:
        return sum(ln.display_ftax  for ln in self.lines)

    @property
    def subtotal_py_final(self) -> float:
        return sum(ln.display_py_final for ln in self.lines)

    @property
    def subtotal_py_ftax(self) -> float:
        return sum(ln.display_py_ftax  for ln in self.lines)

    # ── Raw subtotals (un-flipped) — for net income arithmetic ────────────
    @property
    def subtotal_raw_pbc(self) -> float:
        return sum(ln.pbc_balance    for ln in self.lines)

    @property
    def subtotal_raw_aje(self) -> float:
        return sum(ln.aje_total      for ln in self.lines)

    @property
    def subtotal_raw_adj(self) -> float:
        return sum(ln.adj_balance    for ln in self.lines)

    @property
    def subtotal_raw_rje(self) -> float:
        return sum(ln.rje_total      for ln in self.lines)

    @property
    def subtotal_raw(self) -> float:
        return sum(ln.final_balance  for ln in self.lines)

    @property
    def subtotal_raw_ftje(self) -> float:
        return sum(ln.ftje_total     for ln in self.lines)

    @property
    def subtotal_raw_ftax(self) -> float:
        return sum(ln.ftax_balance   for ln in self.lines)

    @property
    def subtotal_raw_py_final(self) -> float:
        return sum(ln.py_final       for ln in self.lines)

    @property
    def subtotal_raw_py_ftax(self) -> float:
        return sum(ln.py_ftax        for ln in self.lines)


@dataclass
class FinancialReport:
    statement:   str
    entity_type: str
    tax_year:    int
    sections:    list[ReportSection] = field(default_factory=list)

    # ── Balance Sheet totals ───────────────────────────────────────────────
    def _asset_sum(self, attr: str) -> float:
        return sum(getattr(s, attr) for s in self.sections if _is_asset_section(s))

    def _le_sum(self, attr: str) -> float:
        return sum(getattr(s, attr) for s in self.sections if not _is_asset_section(s))

    @property
    def total_assets(self)            -> float: return self._asset_sum("subtotal")
    @property
    def total_assets_pbc(self)        -> float: return self._asset_sum("subtotal_pbc")
    @property
    def total_assets_aje(self)        -> float: return self._asset_sum("subtotal_aje")
    @property
    def total_assets_adj(self)        -> float: return self._asset_sum("subtotal_adj")
    @property
    def total_assets_rje(self)        -> float: return self._asset_sum("subtotal_rje")
    @property
    def total_assets_ftje(self)       -> float: return self._asset_sum("subtotal_ftje")
    @property
    def total_assets_ftax(self)       -> float: return self._asset_sum("subtotal_ftax")
    @property
    def total_assets_py_final(self)   -> float: return self._asset_sum("subtotal_py_final")
    @property
    def total_assets_py_ftax(self)    -> float: return self._asset_sum("subtotal_py_ftax")

    @property
    def total_liabilities_equity(self)          -> float: return self._le_sum("subtotal")
    @property
    def total_liabilities_equity_pbc(self)      -> float: return self._le_sum("subtotal_pbc")
    @property
    def total_liabilities_equity_aje(self)      -> float: return self._le_sum("subtotal_aje")
    @property
    def total_liabilities_equity_adj(self)      -> float: return self._le_sum("subtotal_adj")
    @property
    def total_liabilities_equity_rje(self)      -> float: return self._le_sum("subtotal_rje")
    @property
    def total_liabilities_equity_ftje(self)     -> float: return self._le_sum("subtotal_ftje")
    @property
    def total_liabilities_equity_ftax(self)     -> float: return self._le_sum("subtotal_ftax")
    @property
    def total_liabilities_equity_py_final(self) -> float: return self._le_sum("subtotal_py_final")
    @property
    def total_liabilities_equity_py_ftax(self)  -> float: return self._le_sum("subtotal_py_ftax")

    @property
    def asset_sections(self)           -> list[ReportSection]:
        return [s for s in self.sections if _is_asset_section(s)]

    @property
    def liability_equity_sections(self) -> list[ReportSection]:
        return [s for s in self.sections if not _is_asset_section(s)]

    # NOTE: there is deliberately no is_balanced/bs_difference property here.
    # A working TB only carries income/expense on the P&L, so
    # total_liabilities_equity alone is always understated by exactly the
    # current year's net income — any balance check needs the companion
    # FinancialReport for ProfitAndLoss too (see report_tab.py's
    # _populate_bs / pdf_report.py's _bs_rows for the correct pattern:
    # total_assets - (total_liabilities_equity + pl.net_income)).

    # ── P&L net income (raw un-flipped sums) ──────────────────────────────
    def _ni(self, raw_attr: str) -> float:
        return -sum(getattr(s, raw_attr) for s in self.sections)

    @property
    def net_income_pbc(self)      -> float: return self._ni("subtotal_raw_pbc")
    @property
    def net_income_aje(self)      -> float: return self._ni("subtotal_raw_aje")
    @property
    def net_income_adj(self)      -> float: return self._ni("subtotal_raw_adj")
    @property
    def net_income_rje(self)      -> float: return self._ni("subtotal_raw_rje")
    @property
    def net_income(self)          -> float: return self._ni("subtotal_raw")
    @property
    def net_income_ftje(self)     -> float: return self._ni("subtotal_raw_ftje")
    @property
    def net_income_ftax(self)     -> float: return self._ni("subtotal_raw_ftax")
    @property
    def net_income_py_final(self) -> float: return self._ni("subtotal_raw_py_final")
    @property
    def net_income_py_ftax(self)  -> float: return self._ni("subtotal_raw_py_ftax")


# ── Builder ───────────────────────────────────────────────────────────────────

def build_report(conn, job_id: str, statement: str) -> FinancialReport:
    """
    Build a FinancialReport from the live binder DB.
    Only accounts mapped to a tax line in the requested statement appear.
    Entry lines are split by entry_type so each column is computed independently.
    """
    job_row = conn.execute(
        "SELECT entity_type, tax_year FROM job WHERE job_id = ?", (job_id,)
    ).fetchone()
    entity_type = job_row["entity_type"] if job_row else ""
    tax_year    = job_row["tax_year"]    if job_row else 0

    rows = conn.execute(
        """
        SELECT
            a.account_id,
            a.account_number,
            a.account_name,
            a.account_type,
            a.normal_balance,
            COALESCE(a.flag, '') AS flag,
            COALESCE(a.pbc_balance, 0.0) AS pbc_balance,
            COALESCE(SUM(CASE WHEN je.entry_type = 'AJE'  AND je.status != 'Void'
                              THEN jel.amount ELSE 0 END), 0.0) AS aje_total,
            COALESCE(SUM(CASE WHEN je.entry_type = 'RJE'  AND je.status != 'Void'
                              THEN jel.amount ELSE 0 END), 0.0) AS rje_total,
            COALESCE(SUM(CASE WHEN je.entry_type = 'FTJE' AND je.status != 'Void'
                              THEN jel.amount ELSE 0 END), 0.0) AS ftje_total,
            COALESCE(tl.category, '') AS category,
            tl.section,
            tl.section_sort_order,
            tl.sort_order AS line_sort
        FROM accounts a
        JOIN mappings m
            ON  m.account_id = a.account_id
            AND m.job_id     = a.job_id
        JOIN tax_lines tl
            ON  tl.tax_line_id         = m.tax_line_id
            AND tl.financial_statement = ?
        LEFT JOIN journal_entry_lines jel
            ON jel.account_id = a.account_id
        LEFT JOIN journal_entries je
            ON  je.aje_id = jel.aje_id
            AND je.job_id = a.job_id
        WHERE a.job_id = ?
        GROUP BY a.account_id
        ORDER BY tl.section_sort_order, tl.sort_order, a.account_number
        """,
        (statement, job_id),
    ).fetchall()

    noted_ids: set[str] = {
        r[0] for r in conn.execute(
            "SELECT DISTINCT linked_to_id FROM notes "
            "WHERE job_id = ? AND status = 'Open' AND linked_to_type = 'account'",
            (job_id,),
        ).fetchall()
    }

    py_map: dict[str, tuple[float, float]] = {}
    try:
        for row in conn.execute(
            "SELECT account_id, COALESCE(py_final_balance, 0) AS pf, "
            "COALESCE(py_ftax_balance, 0) AS px "
            "FROM prior_year_balances WHERE job_id = ?",
            (job_id,),
        ).fetchall():
            if row["account_id"]:
                py_map[row["account_id"]] = (float(row["pf"]), float(row["px"]))
    except Exception:
        pass

    sections: dict[str, ReportSection] = {}
    for row in rows:
        sec_name = row["section"]
        if sec_name not in sections:
            sections[sec_name] = ReportSection(
                name=sec_name, sort_order=row["section_sort_order"]
            )
        py_f, py_x = py_map.get(row["account_id"], (0.0, 0.0))
        sections[sec_name].lines.append(ReportLine(
            account_id     = row["account_id"],
            account_number = row["account_number"] or "",
            account_name   = row["account_name"],
            account_type   = row["account_type"] or "",
            normal_balance = row["normal_balance"],
            pbc_balance    = float(row["pbc_balance"]),
            aje_total      = float(row["aje_total"]),
            rje_total      = float(row["rje_total"]),
            ftje_total     = float(row["ftje_total"]),
            category       = row["category"] or "",
            has_open_notes = row["account_id"] in noted_ids,
            flag           = row["flag"] or "",
            py_final       = py_f,
            py_ftax        = py_x,
        ))

    return FinancialReport(
        statement   = statement,
        entity_type = entity_type,
        tax_year    = tax_year,
        sections    = sorted(sections.values(), key=lambda s: s.sort_order),
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

_LE_KEYWORDS = (
    "liability", "liabilities", "equity", "capital", "retained",
    "distribution", "dividend", "draw", "shareholder", "partner",
    "contribution", "deficit", "treasury", "member",
)


def _is_asset_section(section: ReportSection) -> bool:
    # Trust the stored category first — it's the same authoritative field the
    # Excel exporter uses, and unlike section-name keyword matching or an
    # account_type vote, it can't be thrown off by a renamed section or a
    # contra account (e.g. Owner Distributions is account_type "Asset" in
    # this app's own data but tax-line category "equity").
    cat_counts: dict[str, int] = {}
    for ln in section.lines:
        if ln.category:
            cat_counts[ln.category] = cat_counts.get(ln.category, 0) + 1
    if cat_counts:
        asset_votes = sum(n for c, n in cat_counts.items() if c in ASSET_CATEGORIES)
        le_votes    = sum(n for c, n in cat_counts.items()
                         if c in LIABILITY_CATEGORIES or c == CATEGORY_EQUITY)
        if asset_votes or le_votes:
            return asset_votes >= le_votes

    n = section.name.lower()
    if "asset" in n:
        return True
    if any(kw in n for kw in _LE_KEYWORDS):
        return False
    # Use account_type — more reliable than normal_balance for contra accounts
    # (e.g. owner draws are Equity-type but Debit-normal; normal_balance vote
    # would wrongly classify them as assets).
    asset_count = sum(1 for ln in section.lines if ln.account_type == "Asset")
    le_count    = sum(1 for ln in section.lines if ln.account_type in ("Liability", "Equity"))
    if asset_count != le_count:
        return asset_count > le_count
    # Last resort: normal_balance majority vote
    debit_count = sum(1 for ln in section.lines if ln.normal_balance == "Debit")
    return debit_count >= len(section.lines) - debit_count
