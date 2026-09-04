"""
Report tab — financial statement preview with full column progression.

Redesigned to match the clean, flat, workpaper-style statement preview
(client name + statement title + period header; consistent-width columns;
no-fill bold section labels; thin-border subtotals; blue account-name text;
a grouped column-visibility panel with everything visible by default; and a
Notes & Links column so open/cleared notes are visible without leaving the
tab).

Column order (11 total):
  0  Account Name  (always — account numbers are an inline prefix here,
                    toggled by "Hide Account Numbers" in the Columns panel,
                    not a separate column, so they indent along with the
                    account name instead of jutting out unindented at the
                    left edge)
  1  UNADJ BOOK    (toggle, "BOOK" group)
  2  BOOK JE       (toggle, "BOOK" group)
  3  ADJ BOOK      (toggle, "BOOK" group)
  4  RECLASS JE    (toggle, "RECLASS" group)
  5  RECLASSED     (toggle, "RECLASS" group)
  6  TAX JE        (toggle, "TAX" group)
  7  ADJ TAX       (toggle, "TAX" group)
  8  PY Final      (toggle, "PY" group)
  9  PY FTax       (toggle, "PY" group)
 10  Notes & Links (toggle — also carries each account's preparer flag)
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QTreeWidget,
    QTreeWidgetItem, QHeaderView, QMenu, QCheckBox, QPushButton,
    QLabel, QFrame, QWidgetAction, QToolButton,
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QBrush, QFont, QAction

from atbworkup.db.connection import db_connection
from atbworkup.reports.builder import build_report, FinancialReport, ReportSection, ReportLine
from atbworkup.models.groups import get_groups, get_group_members
from atbworkup.models.notes import get_notes
from atbworkup.data.tax_line_categories import (
    CATEGORY_REVENUE, CATEGORY_COGS, CATEGORY_OPEX, CATEGORY_SCHEDULE_K,
)
from atbworkup.exporter.pdf_report import export_statements_pdf

# ── Palette ────────────────────────────────────────────────────────────────────
_NAVY        = "#1A2B4C"
_ACCT_FG     = "#1A6BB5"    # blue account-name text, matching the reference style
_RULE_LIGHT  = "#DDDDDD"
_RULE_HEAVY  = "#999999"
_NOTE_FG     = "#B07800"
_NUM_FAMILY  = "Consolas"

# ── Column constants ───────────────────────────────────────────────────────────
_COL_NAME     =  0
_COL_UNADJ    =  1
_COL_AJE      =  2
_COL_ADJ      =  3
_COL_RJE      =  4
_COL_FINAL    =  5
_COL_FTJE     =  6
_COL_FTAX     =  7
_COL_PY_FINAL =  8
_COL_PY_FTAX  =  9
_COL_NOTES    = 10
_NCOLS        = 11

_HEADERS = [
    "Account Name",
    "UNADJ BOOK", "BOOK JE", "ADJ BOOK",
    "RECLASS JE", "RECLASSED",
    "TAX JE", "ADJ TAX",
    "PY Final", "PY FTax",
    "NOTES & LINKS",
]

# Column groups for the visibility panel — matches how the reference tool
# groups "Hide BOOK / RECLASS / TAX columns" rather than one checkbox per
# column, since a preparer thinks in stages, not individual columns.
_COL_GROUPS = [
    ("BOOK columns",    [_COL_UNADJ, _COL_AJE, _COL_ADJ]),
    ("RECLASS columns", [_COL_RJE, _COL_FINAL]),
    ("TAX columns",     [_COL_FTJE, _COL_FTAX]),
    ("PY columns",      [_COL_PY_FINAL, _COL_PY_FTAX]),
    ("NOTES & LINKS",   [_COL_NOTES]),
]

# Maps each amount-column index to the key pdf_report.py uses for the same
# column, so "hidden in the report view" carries over to the PDF export
# (Notes & Links has no PDF equivalent, so it's left out here).
_PDF_COLS = [
    (_COL_UNADJ, "unadj"), (_COL_AJE, "aje"), (_COL_ADJ, "adj"),
    (_COL_RJE, "rje"), (_COL_FINAL, "final"),
    (_COL_FTJE, "ftje"), (_COL_FTAX, "ftax"),
    (_COL_PY_FINAL, "py_final"), (_COL_PY_FTAX, "py_ftax"),
]

_TREE_STYLE = """
QTreeWidget {
    background-color: #FFFFFF;
    border: none;
    border-top: 1px solid #E0E0E0;
    font-family: "Segoe UI";
    font-size: 13px;
    outline: none;
}
QTreeWidget::item {
    padding: 5px 6px;
    color: #1A1A1A;
    background-color: transparent;
}
QTreeWidget::item:hover {
    background-color: #F5F8FC;
}
QTreeWidget::item:selected {
    background-color: #E4EEFB;
    color: #000000;
}
"""
_TOOLBAR_STYLE = "background: #F7F7F7; border-bottom: 1px solid #E0E0E0; padding: 6px 10px;"
_BTN  = (
    "QPushButton { font-size: 11px; font-weight: bold; padding: 4px 12px; border: 1px solid #CCCCCC;"
    "border-radius: 4px; background: #FFFFFF; color: #333333; }"
    "QPushButton:hover { background: #E4EEFB; }"
    "QPushButton:pressed { background: #D0E0F5; }"
    "QPushButton:checked { background: #D0E4F7; border-color: #1A6BB5; color: #1A2B4C; }"
)
_TOOLBTN = (
    "QToolButton { font-size: 11px; font-weight: bold; padding: 4px 12px; border: 1px solid #CCCCCC;"
    "border-radius: 4px; background: #FFFFFF; color: #333333; }"
    "QToolButton:hover { background: #E4EEFB; }"
    "QToolButton::menu-indicator { image: none; }"
)
_TOGGLE_STYLE = """
QCheckBox { font-size: 11px; color: #333333; spacing: 8px; }
QCheckBox::indicator {
    width: 34px; height: 18px; border-radius: 9px;
    background: #CCCCCC; border: 1px solid #BBBBBB;
}
QCheckBox::indicator:checked {
    background: #1A2B4C; border: 1px solid #1A2B4C;
}
"""


def _fmt(v: float) -> str:
    if abs(v) < 0.005:
        return "—"
    return f"({abs(v):,.2f})" if v < 0 else f"{v:,.2f}"


def _bold() -> QFont:
    f = QFont(); f.setBold(True); return f


def _mono(bold: bool = False) -> QFont:
    f = QFont(_NUM_FAMILY); f.setBold(bold); return f


def _vline() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.VLine)
    f.setStyleSheet("color: #CCCCCC;")
    return f


class ReportTab(QWidget):
    note_requested = Signal(str, str)
    je_requested   = Signal(str, str)

    def __init__(self, path: str | Path, job_id: str, parent=None):
        super().__init__(parent)
        self._path      = Path(path)
        self._job_id    = job_id
        self._collapsed = False
        self._last_bs:        FinancialReport | None = None
        self._last_pl:        FinancialReport | None = None
        self._last_groups:    list[dict]              = []
        self._last_group_map: dict[str, str]          = {}
        self._notes_by_account: dict[str, list[dict]] = {}
        self._entity_name:    str                     = ""
        self._client_name:    str                     = ""
        self._tax_year:       int                     = 0
        self._show_acct_num:  bool                    = True
        self._build_ui()
        self.reprint()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Controls bar ────────────────────────────────────────────────
        bar = QWidget()
        bar.setStyleSheet(_TOOLBAR_STYLE)
        bl  = QHBoxLayout(bar)
        bl.setContentsMargins(10, 5, 10, 5)
        bl.setSpacing(12)

        self._columns_btn = self._build_columns_button()
        bl.addWidget(self._columns_btn)
        bl.addWidget(_vline())

        self._btn_collapse = QPushButton("Collapse All")
        self._btn_collapse.setCheckable(True)
        self._btn_collapse.setStyleSheet(_BTN)
        self._btn_collapse.clicked.connect(self._on_collapse_toggle)

        self._btn_pdf = QPushButton("Export PDF…")
        self._btn_pdf.setStyleSheet(_BTN)
        self._btn_pdf.clicked.connect(self._on_export_pdf)

        bl.addWidget(self._btn_collapse)
        bl.addWidget(self._btn_pdf)
        bl.addStretch()

        root.addWidget(bar)

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        root.addWidget(self._tabs)

        self._bs_tree = self._make_tree()
        self._pl_tree = self._make_tree()
        self._tabs.addTab(self._bs_tree, "Balance Sheet")
        self._tabs.addTab(self._pl_tree, "Profit & Loss")

    # ── Columns dropdown panel ────────────────────────────────────────────

    def _build_columns_button(self) -> QToolButton:
        btn = QToolButton()
        btn.setText("Columns ▾")
        btn.setStyleSheet(_TOOLBTN)
        btn.setPopupMode(QToolButton.InstantPopup)

        panel = QFrame()
        panel.setStyleSheet(
            "QFrame { background: #FFFFFF; border: 1px solid #CCCCCC; border-radius: 4px; }"
        )
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(14, 10, 14, 10)
        pl.setSpacing(8)

        title = QLabel("COLUMN SETTINGS")
        title.setStyleSheet(
            "color: #8A93A5; font-size: 10px; font-weight: bold; letter-spacing: 1px; border: none;"
        )
        pl.addWidget(title)

        # Account numbers aren't a real column — they're an inline prefix on
        # the (always-indented) Account Name text — so toggling them can't
        # go through _apply_cols' column-hide logic; it has to re-render.
        self._cb_acct_num = QCheckBox("Hide Account Numbers")
        self._cb_acct_num.setChecked(False)
        self._cb_acct_num.setStyleSheet(_TOGGLE_STYLE)
        self._cb_acct_num.toggled.connect(self._on_toggle_acct_num)
        pl.addWidget(self._cb_acct_num)

        self._group_checks: list[tuple[QCheckBox, list[int]]] = []
        for label, cols in _COL_GROUPS:
            cb = QCheckBox(f"Hide {label}")
            cb.setChecked(False)   # everything visible by default, per firm preference
            cb.setStyleSheet(_TOGGLE_STYLE)
            cb.toggled.connect(self._apply_cols)
            pl.addWidget(cb)
            self._group_checks.append((cb, cols))

        reset_btn = QPushButton("Firm Default")
        reset_btn.setStyleSheet(_BTN)
        reset_btn.clicked.connect(self._reset_columns_to_default)
        pl.addWidget(reset_btn)

        action = QWidgetAction(btn)
        action.setDefaultWidget(panel)
        menu = QMenu(btn)
        menu.addAction(action)
        btn.setMenu(menu)
        return btn

    def _on_toggle_acct_num(self, checked: bool):
        self._show_acct_num = not checked
        if self._last_bs is not None:
            gby = {g["group_id"]: g for g in self._last_groups}
            self._populate_bs(self._last_bs, self._last_pl, self._last_group_map, gby)
            self._populate_pl(self._last_pl, self._last_group_map, gby)
            self._apply_cols()

    def _reset_columns_to_default(self):
        self._cb_acct_num.setChecked(False)
        for cb, _cols in self._group_checks:
            cb.setChecked(False)

    # ── Public API ────────────────────────────────────────────────────────

    def reprint(self):
        with db_connection(self._path) as conn:
            bs        = build_report(conn, self._job_id, "BalanceSheet")
            pl        = build_report(conn, self._job_id, "ProfitAndLoss")
            groups    = get_groups(conn, self._job_id)
            group_map = get_group_members(conn, self._job_id)
            notes_by_account = _load_notes_by_account(conn, self._job_id)
            job_row   = conn.execute(
                "SELECT client_name, entity_name, tax_year FROM job WHERE job_id = ?",
                (self._job_id,),
            ).fetchone()

        self._last_bs        = bs
        self._last_pl        = pl
        self._last_groups     = groups
        self._last_group_map  = group_map
        self._notes_by_account = notes_by_account
        if job_row:
            self._client_name = job_row["client_name"] or ""
            self._entity_name = job_row["entity_name"] or ""
            self._tax_year    = job_row["tax_year"]    or 0

        gby = {g["group_id"]: g for g in groups}
        self._populate_bs(bs, pl, group_map, gby)
        self._populate_pl(pl, group_map, gby)
        self._apply_cols()
        if self._collapsed:
            self._active_tree().collapseAll()

    # ── Column visibility ─────────────────────────────────────────────────

    def _apply_cols(self, *_):
        hidden_cols: set[int] = set()
        for cb, cols in self._group_checks:
            if cb.isChecked():
                hidden_cols.update(cols)
        for tree in (self._bs_tree, self._pl_tree):
            for c in range(1, _NCOLS):
                tree.setColumnHidden(c, c in hidden_cols)

    def _on_collapse_toggle(self, checked: bool):
        self._collapsed = checked
        self._btn_collapse.setText("Expand All" if checked else "Collapse All")
        t = self._active_tree()
        t.collapseAll() if checked else t.expandAll()

    def _on_export_pdf(self):
        if self._last_bs is None:
            return
        hidden: set[int] = set()
        for cb, cols in self._group_checks:
            if cb.isChecked():
                hidden.update(cols)
        visible_cols = [key for idx, key in _PDF_COLS if idx not in hidden]
        out = export_statements_pdf(
            parent        = self,
            report_bs     = self._last_bs,
            report_pl     = self._last_pl,
            entity_name   = self._entity_name,
            tax_year      = self._tax_year,
            groups        = self._last_groups,
            group_map     = self._last_group_map,
            default_dir   = str(self._path.parent),
            visible_cols  = visible_cols,
            show_acct_num = self._show_acct_num,
        )
        if out:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Export Complete", f"Saved to:\n{out}")

    def _active_tree(self) -> QTreeWidget:
        return self._bs_tree if self._tabs.currentIndex() == 0 else self._pl_tree

    # ── Tree factory ──────────────────────────────────────────────────────

    def _make_tree(self) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setColumnCount(_NCOLS)
        tree.setHeaderLabels(_HEADERS)
        # Flat, presentation-style layout: indentation is drawn manually per
        # row (see _indent()) rather than via native tree nesting, so every
        # row type — category, section, account, subtotal — lines up on the
        # same consistent grid regardless of whether it's a true tree parent
        # or a synthetic "stays visible when collapsed" sibling. Account
        # GROUPS (a real, occasionally-nested feature) still use real
        # parent/child structure so Collapse All / Expand All keeps working;
        # they just no longer draw an expand arrow.
        tree.setRootIsDecorated(False)
        tree.setIndentation(0)
        tree.setAlternatingRowColors(False)
        tree.setSelectionBehavior(QTreeWidget.SelectRows)
        tree.setStyleSheet(_TREE_STYLE)
        tree.setContextMenuPolicy(Qt.CustomContextMenu)
        tree.customContextMenuRequested.connect(
            lambda pos, t=tree: self._ctx_menu(t, pos)
        )
        hdr = tree.header()
        hdr.setSectionResizeMode(_COL_NAME, QHeaderView.Stretch)
        for c in range(1, _NCOLS):
            hdr.setSectionResizeMode(c, QHeaderView.Interactive)
            tree.setColumnWidth(c, 108 if c != _COL_NOTES else 130)
        hdr.setDefaultAlignment(Qt.AlignCenter)
        hdr.setStretchLastSection(False)
        hdr.setStyleSheet(
            f"QHeaderView::section {{"
            f"  background: {_NAVY}; color: white;"
            f"  font-family: 'Segoe UI'; font-size: 11px; font-weight: bold;"
            f"  padding: 5px 8px; border: none; border-right: 1px solid #2A3B5C;"
            f"}}"
        )
        hdr.setContextMenuPolicy(Qt.CustomContextMenu)
        hdr.customContextMenuRequested.connect(
            lambda pos, t=tree: self._on_report_header_menu(t, pos)
        )
        return tree

    def _on_report_header_menu(self, tree: QTreeWidget, pos):
        menu = QMenu(self)
        reset = menu.addAction("Reset Column Widths")
        if menu.exec(tree.header().mapToGlobal(pos)) == reset:
            for c in range(1, _NCOLS):
                tree.setColumnWidth(c, 108 if c != _COL_NOTES else 130)

    # ── Statement header (client / statement / period) ─────────────────────

    def _write_title(self, tree: QTreeWidget, statement_label: str):
        """Centered 3-line title block, matching a printed financial
        statement: client name, statement title, period-ending line.

        setFirstColumnSpanned(True) merges every column into one wide cell
        for this row — without it, "centering" only centers within the
        narrow Account Name column, not the full table width, which looks
        more off-center the more columns are visible.
        """
        period = f"Period ending: December 31, {self._tax_year}" if self._tax_year else ""
        name = self._client_name or self._entity_name
        for text, font_size, bold, color in (
            (name,            13, True,  _NAVY),
            (statement_label, 13, True,  _NAVY),
            (period,          10, False, "#555555"),
        ):
            item = QTreeWidgetItem([""] * _NCOLS)
            item.setFlags(Qt.NoItemFlags)
            item.setText(0, text)
            item.setTextAlignment(0, Qt.AlignHCenter | Qt.AlignVCenter)
            f = QFont(); f.setPointSize(font_size); f.setBold(bold)
            item.setFont(0, f)
            item.setForeground(0, QBrush(QColor(color)))
            tree.addTopLevelItem(item)
            item.setFirstColumnSpanned(True)
        _spacer(tree, 10)

    # ── Balance Sheet ─────────────────────────────────────────────────────

    def _populate_bs(self, r: FinancialReport, pl: FinancialReport | None,
                     gmap: dict, gby: dict):
        t = self._bs_tree
        t.clear()
        self._write_title(t, "BALANCE SHEET")
        nba = self._notes_by_account

        _category(t, "ASSETS")
        for sec in r.asset_sections:
            _section(t, sec, gmap, gby, nba, self._show_acct_num)
        _grand_total(t, "TOTAL ASSETS",
                     r.total_assets_pbc, r.total_assets_aje, r.total_assets_adj,
                     r.total_assets_rje, r.total_assets,
                     r.total_assets_ftje, r.total_assets_ftax,
                     r.total_assets_py_final, r.total_assets_py_ftax)
        _spacer(t, 16)

        _category(t, "LIABILITIES & EQUITY")
        for sec in r.liability_equity_sections:
            _section(t, sec, gmap, gby, nba, self._show_acct_num)

        # Current-year net income from P&L — carries into equity for balance check.
        # A working TB has income/expense mapped to P&L, so equity only has the
        # prior-period balance. We inject net income here so the BS balances.
        ni_pbc = ni_aje = ni_adj = ni_rje = ni = ni_ftje = ni_ftax = ni_pyf = ni_pyx = 0.0
        if pl:
            ni_pbc  = pl.net_income_pbc
            ni_aje  = pl.net_income_aje
            ni_adj  = pl.net_income_adj
            ni_rje  = pl.net_income_rje
            ni      = pl.net_income
            ni_ftje = pl.net_income_ftje
            ni_ftax = pl.net_income_ftax
            ni_pyf  = pl.net_income_py_final
            ni_pyx  = pl.net_income_py_ftax

        if abs(ni) >= 0.005:
            _ni_row(t, ni_pbc, ni_aje, ni_adj, ni_rje, ni,
                    ni_ftje, ni_ftax, ni_pyf, ni_pyx)

        # Adjusted L&E grand total includes current-year net income
        _grand_total(t, "TOTAL LIABILITIES & EQUITY",
                     r.total_liabilities_equity_pbc  + ni_pbc,
                     r.total_liabilities_equity_aje  + ni_aje,
                     r.total_liabilities_equity_adj  + ni_adj,
                     r.total_liabilities_equity_rje  + ni_rje,
                     r.total_liabilities_equity       + ni,
                     r.total_liabilities_equity_ftje + ni_ftje,
                     r.total_liabilities_equity_ftax + ni_ftax,
                     r.total_liabilities_equity_py_final + ni_pyf,
                     r.total_liabilities_equity_py_ftax  + ni_pyx)
        _spacer(t, 8)

        adj_le = r.total_liabilities_equity + ni
        diff   = r.total_assets - adj_le
        if abs(diff) < 0.005:
            _status(t, "✓  In Balance", "#1A7A1A")
        else:
            _status(t, f"⚠  Out of Balance  —  difference: {_fmt(diff)}", "#CC0000")

    # ── P&L ───────────────────────────────────────────────────────────────

    def _populate_pl(self, r: FinancialReport, gmap: dict, gby: dict):
        t = self._pl_tree
        t.clear()
        self._write_title(t, "INCOME STATEMENT")
        nba = self._notes_by_account
        san = self._show_acct_num

        # Classify every section up front so Gross Profit / Operating Income
        # use ALL sections of the relevant category regardless of how many
        # sections carry it (a chart of accounts commonly splits COGS into
        # e.g. "COGS - Materials" / "COGS - Labor") — injecting mid-loop on
        # the FIRST section of a category seen previously both undercounted
        # sections of that category that came later and misplaced the row.
        section_cats = [_section_category(sec) for sec in r.sections]
        rev_secs  = [s for s, c in zip(r.sections, section_cats) if c == CATEGORY_REVENUE]
        cogs_secs = [s for s, c in zip(r.sections, section_cats) if c == CATEGORY_COGS]
        opex_secs = [s for s, c in zip(r.sections, section_cats) if c == CATEGORY_OPEX]
        last_cogs_index = max(
            (i for i, c in enumerate(section_cats) if c == CATEGORY_COGS), default=-1
        )
        last_opex_index = max(
            (i for i, c in enumerate(section_cats) if c == CATEGORY_OPEX), default=-1
        )

        def _gp(attr: str) -> float:
            # Both subtotals display positive (revenue is flipped for
            # display, COGS is already positive debit-normal) — Gross
            # Profit is their DIFFERENCE, not their sum; summing here was
            # the same "blind sum adds instead of subtracts" bug documented
            # elsewhere in this app.
            return (sum(getattr(s, attr) for s in rev_secs)
                    - sum(getattr(s, attr) for s in cogs_secs))

        def _oi(attr: str) -> float:
            # Operating Income = Gross Profit less operating expenses
            # (Deductions). Computed independently of whether a Gross Profit
            # row was actually rendered (e.g. a service business with no
            # COGS sections at all still has an Operating Income).
            return _gp(attr) - sum(getattr(s, attr) for s in opex_secs)

        for i, sec in enumerate(r.sections):
            _section(t, sec, gmap, gby, nba, san)
            if i == last_cogs_index and rev_secs:
                _grand_total(t, "Gross Profit",
                             _gp("subtotal_pbc"), _gp("subtotal_aje"), _gp("subtotal_adj"),
                             _gp("subtotal_rje"), _gp("subtotal"),
                             _gp("subtotal_ftje"), _gp("subtotal_ftax"),
                             _gp("subtotal_py_final"), _gp("subtotal_py_ftax"))
                _spacer(t, 10)
            if i == last_opex_index:
                _grand_total(t, "Operating Income",
                             _oi("subtotal_pbc"), _oi("subtotal_aje"), _oi("subtotal_adj"),
                             _oi("subtotal_rje"), _oi("subtotal"),
                             _oi("subtotal_ftje"), _oi("subtotal_ftax"),
                             _oi("subtotal_py_final"), _oi("subtotal_py_ftax"))
                _spacer(t, 10)
        _grand_total(t, "NET INCOME / (LOSS)",
                     r.net_income_pbc, r.net_income_aje, r.net_income_adj,
                     r.net_income_rje, r.net_income,
                     r.net_income_ftje, r.net_income_ftax,
                     r.net_income_py_final, r.net_income_py_ftax)

    # ── Context menu ──────────────────────────────────────────────────────

    def _ctx_menu(self, tree: QTreeWidget, pos):
        item = tree.itemAt(pos)
        if not item:
            return
        aid  = item.data(0, Qt.UserRole)
        name = item.data(0, Qt.UserRole + 1)
        if not aid:
            return
        menu = QMenu(self)
        a1 = QAction("Add Note…", self)
        a2 = QAction("Create Journal Entry…", self)
        a1.triggered.connect(lambda: self.note_requested.emit(aid, name))
        a2.triggered.connect(lambda: self.je_requested.emit(aid, name))
        menu.addAction(a1)
        menu.addAction(a2)
        menu.exec(tree.viewport().mapToGlobal(pos))


# ── Module-level item builders ─────────────────────────────────────────────────

def _load_notes_by_account(conn, job_id: str) -> dict[str, list[dict]]:
    """{account_id: [note dicts]} for every note (open + cleared/resolved)
    linked to an account, so the Notes & Links column has something to show
    without the user having to leave the statement preview."""
    notes = get_notes(conn, job_id, status_filter="All")
    out: dict[str, list[dict]] = {}
    for n in notes:
        if n.get("linked_to_type") == "account" and n.get("linked_to_id"):
            out.setdefault(n["linked_to_id"], []).append(n)
    return out


def _indent(text: str, level: int) -> str:
    return ("    " * level) + text


def _vals(sec_or_ln) -> list[str]:
    """Return the 9 formatted data values for a section or line."""
    return [
        _fmt(sec_or_ln.subtotal_pbc),
        _fmt(sec_or_ln.subtotal_aje),
        _fmt(sec_or_ln.subtotal_adj),
        _fmt(sec_or_ln.subtotal_rje),
        _fmt(sec_or_ln.subtotal),
        _fmt(sec_or_ln.subtotal_ftje),
        _fmt(sec_or_ln.subtotal_ftax),
        _fmt(sec_or_ln.subtotal_py_final),
        _fmt(sec_or_ln.subtotal_py_ftax),
    ]


def _make_item(label: str, data_vals: list[str]) -> QTreeWidgetItem:
    return QTreeWidgetItem([label] + data_vals + [""])


def _style_num_cols(item: QTreeWidgetItem, bold: bool = False):
    """Apply monospace font + right-align to all numeric columns. Every
    amount column reads in the same plain dark tone — no per-column rainbow
    tinting — matching the clean, uniform look of a printed statement."""
    for col in range(1, _NCOLS - 1):
        item.setFont(col, _mono(bold))
        item.setTextAlignment(col, Qt.AlignRight | Qt.AlignVCenter)


_FLAG_SYMBOLS = {
    # Matches financial_grid.py's _FLAG_DISPLAY exactly, so a flag reads the
    # same in the TB grid and the report preview.
    "question": ("⚑", "#f9a825"),
    "reviewed": ("✓", "#2e7d32"),
    "issue":    ("✗", "#c62828"),
}


def _write_notes_cell(item: QTreeWidgetItem, ln: ReportLine,
                      notes_by_account: dict[str, list[dict]]):
    notes = notes_by_account.get(ln.account_id) or []
    open_notes = [n for n in notes if n.get("status") == "Open"]

    flag_symbol, flag_color = _FLAG_SYMBOLS.get(ln.flag, ("", None))
    note_label = note_color = ""
    if notes:
        note_label = f"🗒 {len(notes)}" if not open_notes else f"🗒 {len(open_notes)} open"
        note_color = "#B07800" if open_notes else "#888888"

    parts = [p for p in (flag_symbol, note_label) if p]
    if not parts:
        return
    # The flag is the preparer's own explicit call-out, so it wins the
    # cell's single text color when both a flag and notes are present.
    color = flag_color or note_color
    item.setText(_COL_NOTES, "  ".join(parts))
    item.setTextAlignment(_COL_NOTES, Qt.AlignCenter)
    item.setForeground(_COL_NOTES, QBrush(QColor(color)))
    f = QFont(); f.setBold(bool(open_notes) or bool(flag_symbol))
    item.setFont(_COL_NOTES, f)

    tooltip_lines = [f"Flag: {ln.flag}"] if flag_symbol else []
    tooltip_lines += [
        f"[{n.get('note_type', 'preparer')}/{n['status']}] {n['body'][:120]}"
        for n in notes[:8]
    ]
    item.setToolTip(_COL_NOTES, "\n".join(tooltip_lines))


def _category(tree: QTreeWidget, label: str):
    item = QTreeWidgetItem([""] * _NCOLS)
    item.setFlags(Qt.ItemIsEnabled)
    item.setText(_COL_NAME, _indent(label, 0))
    item.setFont(_COL_NAME, _bold())
    item.setForeground(_COL_NAME, QBrush(QColor(_NAVY)))
    item.setTextAlignment(_COL_NAME, Qt.AlignLeft | Qt.AlignVCenter)
    tree.addTopLevelItem(item)


def _add_item(parent, item: QTreeWidgetItem):
    """Add `item` under `parent`, which is either the QTreeWidget itself
    (top-level) or a QTreeWidgetItem (a real child — used for sections'
    accounts/groups and groups' members, so Collapse All / Expand All has
    something real to collapse)."""
    if isinstance(parent, QTreeWidget):
        parent.addTopLevelItem(item)
    else:
        parent.addChild(item)


def _display_section_name(sec: ReportSection) -> str:
    """Schedule K pass-through items read to a client as "Other Income" —
    the underlying tax-line section name (e.g. "Schedule K — Pass-Through")
    stays as-is everywhere else (Tax Grouping/Excel/DB), this is purely a
    report-view display label."""
    if _section_category(sec) == CATEGORY_SCHEDULE_K:
        return "Other Income"
    return sec.name


def _section(tree: QTreeWidget, sec: ReportSection, gmap: dict, gby: dict,
            notes_by_account: dict, show_acct_num: bool = True):
    # No-fill bold section label. Accounts/groups become real CHILDREN of
    # this header (so Collapse All / Expand All actually hides them), while
    # the subtotal stays a top-level sibling — same GAAP-style behavior as
    # before this file's redesign: the subtotal is still visible even when
    # the section is collapsed.
    name = _display_section_name(sec)
    hdr = QTreeWidgetItem([""] * _NCOLS)
    hdr.setFlags(Qt.ItemIsEnabled)
    hdr.setText(_COL_NAME, _indent(name, 0))
    hdr.setFont(_COL_NAME, _bold())
    hdr.setForeground(_COL_NAME, QBrush(QColor(_NAVY)))
    hdr.setTextAlignment(_COL_NAME, Qt.AlignLeft | Qt.AlignVCenter)
    tree.addTopLevelItem(hdr)

    # Split into grouped / ungrouped
    grouped: dict[str, list[ReportLine]] = {}
    ungrouped: list[ReportLine] = []
    for ln in sec.lines:
        gid = gmap.get(ln.account_id)
        if gid and gid in gby:
            grouped.setdefault(gid, []).append(ln)
        else:
            ungrouped.append(ln)

    all_gids: set[str] = set(grouped.keys())
    for gid in list(all_gids):
        g = gby.get(gid)
        while g and g.get("parent_id"):
            all_gids.add(g["parent_id"])
            g = gby.get(g["parent_id"])

    root_gids = sorted(
        [g for g in all_gids if gby.get(g, {}).get("parent_id") not in all_gids],
        key=lambda g: gby.get(g, {}).get("sort_order", 0),
    )
    for gid in root_gids:
        _group_node(hdr, gid, gby, grouped, all_gids, notes_by_account, level=1, show_acct_num=show_acct_num)
    for ln in ungrouped:
        _acct(hdr, ln, notes_by_account, level=1, show_acct_num=show_acct_num)
    hdr.setExpanded(True)

    # Subtotal — bold, no fill, thin top border, same tier as the section label.
    sub = _make_item(_indent(f"Total {name}", 0), _vals(sec))
    sub.setFlags(Qt.ItemIsEnabled)
    sub.setFont(_COL_NAME, _bold())
    sub.setTextAlignment(_COL_NAME, Qt.AlignLeft | Qt.AlignVCenter)
    _style_num_cols(sub, bold=True)
    _rule(tree)
    tree.addTopLevelItem(sub)

    _spacer(tree, 6)


def _group_node(parent, gid: str, gby: dict,
                grouped: dict, all_gids: set, notes_by_account: dict, level: int,
                show_acct_num: bool = True):
    group = gby.get(gid)
    if not group:
        return
    lines = _collect(gid, gby, grouped, all_gids)
    if not lines:
        return

    dv = [
        _fmt(sum(l.display_pbc      for l in lines)),
        _fmt(sum(l.display_aje      for l in lines)),
        _fmt(sum(l.display_adj      for l in lines)),
        _fmt(sum(l.display_rje      for l in lines)),
        _fmt(sum(l.display_final    for l in lines)),
        _fmt(sum(l.display_ftje     for l in lines)),
        _fmt(sum(l.display_ftax     for l in lines)),
        _fmt(sum(l.display_py_final for l in lines)),
        _fmt(sum(l.display_py_ftax  for l in lines)),
    ]
    g_item = _make_item(_indent(group["name"], level), dv)
    g_item.setFlags(Qt.ItemIsEnabled)
    g_item.setFont(_COL_NAME, _bold())
    g_item.setTextAlignment(_COL_NAME, Qt.AlignLeft | Qt.AlignVCenter)
    _style_num_cols(g_item, bold=True)
    g_item.setForeground(_COL_NAME, QBrush(QColor(_NAVY)))
    _add_item(parent, g_item)

    child_gids = sorted(
        [g for g in all_gids if gby.get(g, {}).get("parent_id") == gid],
        key=lambda g: gby.get(g, {}).get("sort_order", 0),
    )
    for cid in child_gids:
        _group_node(g_item, cid, gby, grouped, all_gids, notes_by_account, level=level + 1, show_acct_num=show_acct_num)
    for ln in grouped.get(gid, []):
        _acct(g_item, ln, notes_by_account, level=level + 1, show_acct_num=show_acct_num)

    # Subtotal at the bottom of the group (GAAP style) — a real child of the
    # group, so it (unlike the section-level subtotal) hides along with the
    # rest of the group when collapsed.
    sub = _make_item(_indent(f"Total {group['name']}", level), dv)
    sub.setFlags(Qt.ItemIsEnabled)
    sub.setFont(_COL_NAME, _bold())
    sub.setTextAlignment(_COL_NAME, Qt.AlignLeft | Qt.AlignVCenter)
    _style_num_cols(sub, bold=True)
    sub.setForeground(_COL_NAME, QBrush(QColor(_NAVY)))
    _rule(g_item)
    g_item.addChild(sub)
    g_item.setExpanded(True)


def _collect(gid, gby, grouped, all_gids):
    lines = list(grouped.get(gid, []))
    for g in all_gids:
        if gby.get(g, {}).get("parent_id") == gid:
            lines.extend(_collect(g, gby, grouped, all_gids))
    return lines


def _section_category(sec: ReportSection) -> str:
    """Majority-vote the section's stored tax-line category — used to find
    Revenue/COGS sections for the Gross Profit break, instead of the old
    section-name keyword match (fragile against a renamed section, and the
    same class of bug fixed for _is_asset_section in builder.py)."""
    counts: dict[str, int] = {}
    for ln in sec.lines:
        if ln.category:
            counts[ln.category] = counts.get(ln.category, 0) + 1
    if not counts:
        return ""
    return max(counts, key=counts.get)


def _acct(parent, ln: ReportLine, notes_by_account: dict, level: int = 1,
         show_acct_num: bool = True):
    # Account number is an inline prefix on the name, not a separate
    # column — it indents along with the account name instead of jutting
    # out unindented at the left edge, and "hideable" just means leaving
    # the prefix off.
    prefix = f"{ln.account_number}  " if (show_acct_num and ln.account_number) else ""
    warn = "⚠  " if ln.has_open_notes else ""
    label = _indent(f"{prefix}{warn}{ln.account_name}", level)
    dv = [
        _fmt(ln.display_pbc),
        _fmt(ln.display_aje),
        _fmt(ln.display_adj),
        _fmt(ln.display_rje),
        _fmt(ln.display_final),
        _fmt(ln.display_ftje),
        _fmt(ln.display_ftax),
        _fmt(ln.display_py_final),
        _fmt(ln.display_py_ftax),
    ]
    item = _make_item(label, dv)
    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
    item.setTextAlignment(_COL_NAME, Qt.AlignLeft | Qt.AlignVCenter)
    item.setForeground(_COL_NAME, QBrush(QColor(_NOTE_FG if ln.has_open_notes else _ACCT_FG)))
    _style_num_cols(item, bold=False)
    item.setData(0, Qt.UserRole, ln.account_id)
    item.setData(0, Qt.UserRole + 1, ln.account_name)
    _write_notes_cell(item, ln, notes_by_account)
    _add_item(parent, item)


def _ni_row(tree: QTreeWidget,
            pbc: float, aje: float, adj: float,
            rje: float, final: float,
            ftje: float, ftax: float,
            py_final: float = 0.0, py_ftax: float = 0.0):
    """Inject a 'Current Year Net Income' row into the equity section of the BS."""
    dv = [_fmt(pbc), _fmt(aje), _fmt(adj), _fmt(rje), _fmt(final),
          _fmt(ftje), _fmt(ftax), _fmt(py_final), _fmt(py_ftax)]
    item = _make_item(_indent("Current Year Net Income", 1), dv)
    item.setFlags(Qt.ItemIsEnabled)
    item.setFont(_COL_NAME, _bold())
    item.setTextAlignment(_COL_NAME, Qt.AlignLeft | Qt.AlignVCenter)
    _style_num_cols(item, bold=True)
    ni_color = "#1A7A1A" if final >= 0 else "#CC0000"
    item.setForeground(_COL_NAME, QBrush(QColor(ni_color)))
    item.setForeground(_COL_FINAL, QBrush(QColor(ni_color)))
    tree.addTopLevelItem(item)


def _grand_total(tree: QTreeWidget, label: str,
                 pbc: float, aje: float, adj: float,
                 rje: float, final: float,
                 ftje: float, ftax: float,
                 py_final: float = 0.0, py_ftax: float = 0.0):
    dv = [_fmt(pbc), _fmt(aje), _fmt(adj), _fmt(rje), _fmt(final),
          _fmt(ftje), _fmt(ftax), _fmt(py_final), _fmt(py_ftax)]
    item = _make_item(_indent(label, 0), dv)
    item.setFlags(Qt.ItemIsEnabled)
    item.setFont(_COL_NAME, _bold())
    item.setTextAlignment(_COL_NAME, Qt.AlignLeft | Qt.AlignVCenter)
    _style_num_cols(item, bold=True)
    _rule(tree, heavy=True)
    tree.addTopLevelItem(item)


def _rule(parent, heavy: bool = False):
    """A hairline row — QTreeWidgetItem has no per-item border property, so
    a top border is drawn as a thin filled row immediately above the total
    it belongs to. `heavy` is used for grand totals (Total Assets, Total
    Liabilities & Equity, Net Income) so they read as more final than an
    ordinary section subtotal. `parent` is the QTreeWidget for a top-level
    rule, or a QTreeWidgetItem to nest the rule as a real child (e.g. right
    before a group's own subtotal, so it collapses along with the group)."""
    item = QTreeWidgetItem([""] * _NCOLS)
    item.setFlags(Qt.NoItemFlags)
    clr = QColor(_RULE_HEAVY if heavy else _RULE_LIGHT)
    height = QSize(0, 2 if heavy else 1)
    for col in range(_NCOLS):
        item.setBackground(col, QBrush(clr))
        # Qt sizes a row by the MAX size hint across every column in that
        # row — setting this on column 0 alone leaves column 1 (Account
        # Name, always visible) to fall back to normal font-metric height,
        # so the row renders full-height instead of as a hairline.
        item.setData(col, Qt.SizeHintRole, height)
    _add_item(parent, item)


def _status(tree: QTreeWidget, text: str, color: str):
    item = QTreeWidgetItem([""] * _NCOLS)
    item.setFlags(Qt.ItemIsEnabled)
    item.setText(_COL_NAME, text)
    item.setFont(_COL_NAME, _bold())
    item.setForeground(_COL_NAME, QBrush(QColor(color)))
    item.setTextAlignment(_COL_NAME, Qt.AlignLeft | Qt.AlignVCenter)
    tree.addTopLevelItem(item)


def _spacer(parent, h: int = 6):
    item = QTreeWidgetItem([""] * _NCOLS)
    item.setFlags(Qt.NoItemFlags)
    size = QSize(0, h)
    for col in range(_NCOLS):
        item.setData(col, Qt.SizeHintRole, size)
    _add_item(parent, item)
