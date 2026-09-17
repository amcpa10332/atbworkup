"""
Report tab — financial statement preview with full column progression.

Visual design is deliberately lifted from the firm's own .bta Excel export
(blueprinttb/exporter/review_package.py) rather than invented independently —
that output is the thing preparers already trust the look of. Same palette,
same tiering:
  - Column header bar + title banner: navy fill, white bold text
  - Statement title (2nd line): platinum fill, navy bold text
  - FS/entry-type category banner (ASSETS, BALANCE SHEET, AJE, ...): black
    fill, white bold text
  - Tax-line header (Cash, Trade Notes & Accounts Receivable, ...): light
    navy-tinted blue fill, navy text
  - Subtotal / total rows: platinum fill, bold black text
  - Account/data rows: white, plain black text, thin bottom rule (mimics
    the exporter's per-cell Excel border)

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
from PySide6.QtGui import QColor, QBrush, QFont, QAction, QPen

from blueprinttb.db.connection import db_connection
from blueprinttb.reports.builder import build_report, FinancialReport, ReportSection, ReportLine
from blueprinttb.models.groups import get_groups, get_group_members
from blueprinttb.models.notes import get_notes
from blueprinttb.models.journal_entries import get_entries, get_lines
from blueprinttb.models.tax_grouping_ties import (
    get_ties, cycle_tie_flag, invalidate_stale_ties,
)
from blueprinttb.data.tax_line_categories import (
    CATEGORY_REVENUE, CATEGORY_COGS, CATEGORY_OPEX, CATEGORY_SCHEDULE_K,
    CATEGORY_CURRENT_ASSET, CATEGORY_EQUITY, LIABILITY_CATEGORIES,
)
from blueprinttb.exporter.pdf_report import export_statements_pdf
from blueprinttb.ui.theme import RoleBackgroundDelegate

# ── Palette (lifted directly from review_package.py's _NAVY/_WHITE/_PLAT/
#    _LIGHT/_BLACK constants) ────────────────────────────────────────────
_NAVY   = "#1A2B4C"
_WHITE  = "#FFFFFF"
_PLAT   = "#E5E5E5"
_LIGHT  = "#D0D8E8"
_BLACK  = "#000000"

_NOTE_FG     = "#B07800"
_NUM_FAMILY  = "Consolas"

# Rule colors mimic the exporter's thin (#CCCCCC) vs. medium/double (black)
# Excel cell borders — the only way a QTreeWidgetItem can fake a per-cell
# border is a thin filled row immediately above it (see _rule()).
_RULE_LIGHT  = "#CCCCCC"
_RULE_HEAVY  = _BLACK

# Header/shading tiers, matching the exporter tab-for-tab:
#   title banner / column header bar -> navy, white text
#   statement label (2nd title line)  -> platinum, navy text
#   FS category banner (Balance Sheet / ASSETS / entry-type) -> black, white
#   bucket header (ReportSection, e.g. "Current Assets")     -> navy, white
#   tax-line header (e.g. "Cash", one tier finer than a bucket, matching
#     ReportLine.line_name)                                  -> light blue, navy
#   subtotal / grand-total rows                               -> platinum, black
_TITLE_BG      = _NAVY
_TITLE_FG      = _WHITE
_TITLE2_BG     = _PLAT
_TITLE2_FG     = _NAVY
_CATEGORY_BG   = _BLACK
_CATEGORY_FG   = _WHITE
_BUCKET_BG     = _NAVY
_BUCKET_FG     = _WHITE
_TAXLINE_BG    = _LIGHT
_TAXLINE_FG    = _NAVY
# App-only tier (custom account groups) that has no Excel equivalent -- a
# darker tint than the tax-line row it nests under, so the two stay visually
# distinct instead of blurring together at the same light blue.
_GROUP_BG      = "#AEBEDA"
_GROUP_FG      = _NAVY
_SUBTOTAL_BG   = _PLAT
_SUBTOTAL_FG   = _BLACK
_GRANDTOTAL_BG = _PLAT
_GRANDTOTAL_FG = _BLACK

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

# Tax Grouping tab only: one extra trailing column for the tie-out flag
# (see tax_grouping_ties.py) -- a preparer's own "entered on the return and
# tied out" mark, independent of the Trial Balance's account flag. Not
# added to _NCOLS/_HEADERS since the Balance Sheet/P&L/Journal Entries tabs
# don't have this column at all.
_COL_TIE   = _NCOLS
_TAX_NCOLS = _NCOLS + 1
_TAX_HEADERS = _HEADERS + ["TIE OUT"]

_TIE_FLAG_DISPLAY = {
    "question": ("⚑", "#f9a825"),   # never click-reachable -- set only by staleness detection
    "reviewed": ("✓", "#2e7d32"),
    None:       ("", "#6B7280"),
}
_TIE_BOX_BG      = "#EBEDF2"          # same light gray as the TB grid's flag box
_TIE_BOX_OUTLINE = QColor(0, 0, 0, 90)   # faint (~35% opacity) black outline

# ── Journal Entries tab ─────────────────────────────────────────────────
# Column-for-column match to review_package.py's _write_journal_entries_tab
# (Entry # | Description | Account # | Account Name | DR | CR | Memo).
_JE_COL_ENTRY    = 0
_JE_COL_DESC     = 1
_JE_COL_ACCTNUM  = 2
_JE_COL_ACCTNAME = 3
_JE_COL_DR       = 4
_JE_COL_CR       = 5
_JE_COL_MEMO     = 6
_JE_NCOLS        = 7
_JE_HEADERS = [
    "Entry #", "Description", "Account #", "Account Name", "DR", "CR", "Memo",
]
_JE_TYPE_LABELS = {
    "AJE":  "Adjusting Journal Entries",
    "RJE":  "Reclassifying Journal Entries",
    "FTJE": "Federal Tax Journal Entries",
}
_JE_TYPE_ORDER = ["AJE", "RJE", "FTJE"]

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
    /* No `color:` here on purpose -- Qt Style Sheets, once ANY property on
       ::item is set, override QTreeWidgetItem.setForeground() (Qt::Fore-
       groundRole) for the item's normal state with whatever `color` this
       rule declares. A previous `color: #1A1A1A` here silently repainted
       every custom foreground (white banner text, navy tax-line text, ...)
       as dark gray, which is exactly what made white text on a dark fill
       "unreadable": the fill wasn't rendering either (see
       theme.RoleBackgroundDelegate), and the text that was meant to sit on
       it wasn't the color it was told to be. Confirmed with an isolated
       QTreeWidget repro reading back actual painted pixel colors. Leaving
       `color` out lets every row's own setForeground() call win, with the
       normal Qt palette default for anything that doesn't set one. */
    padding: 6px 8px;
    background-color: transparent;
    border-bottom: 1px solid #E5E5E5;
}
QTreeWidget::item:hover {
    background-color: #F5F8FC;
}
QTreeWidget::item:selected {
    background-color: #E4EEFB;
    color: #000000;
}
"""


class _TieBoxDelegate(RoleBackgroundDelegate):
    """Same background-role fix as RoleBackgroundDelegate, plus a faint
    outline drawn around the tie-out flag column on the Tax Grouping tab --
    matches the Trial Balance grid's own flag box (financial_grid.py's
    _FlagBoxDelegate) so the two look and behave the same, even though
    their underlying data is completely separate."""

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        if index.column() != _COL_TIE:
            return
        bg = index.data(Qt.BackgroundRole)
        if bg is not None and bg.color() == QColor(_TIE_BOX_BG):
            painter.save()
            painter.setPen(QPen(_TIE_BOX_OUTLINE, 1))
            rect = option.rect.adjusted(6, 4, -6, -4)
            painter.drawRect(rect)
            painter.restore()


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

    def __init__(self, path: str | Path, job_id: str, parent=None,
                default_export_dir: str | Path | None = None,
                performed_by: str = ""):
        super().__init__(parent)
        self._path      = Path(path)
        self._job_id    = job_id
        self._performed_by = performed_by
        # `path` is the app's ephemeral working SQLite file, always under the
        # system temp dir (see utils/naming.py:temp_working_path) -- NOT the
        # user's actual workpaper folder. Defaulting the PDF export dialog
        # to self._path.parent silently pointed it at %TEMP%\BlueprintTB
        # instead of wherever the real .bta.xlsx lives, which is the
        # workpaper folder chosen at start. The caller (WorkupWindow) passes
        # that real folder in explicitly; only fall back to the temp dir
        # when it genuinely isn't available yet (no source file saved yet).
        self._default_export_dir = Path(default_export_dir) if default_export_dir else self._path.parent
        self._collapsed = False
        self._last_bs:        FinancialReport | None = None
        self._last_pl:        FinancialReport | None = None
        self._last_groups:    list[dict]              = []
        self._last_group_map: dict[str, str]          = {}
        self._notes_by_account: dict[str, list[dict]] = {}
        self._tie_values:     dict[str, float]        = {}
        self._last_ties:      dict[str, dict]          = {}
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

        self._bs_tree  = self._make_tree()
        self._pl_tree  = self._make_tree()
        self._tax_tree = self._make_tree(tie_col=True)
        self._je_tree  = self._make_je_tree()
        self._tabs.addTab(self._bs_tree, "Balance Sheet")
        self._tabs.addTab(self._pl_tree, "Profit & Loss")
        self._tabs.addTab(self._tax_tree, "Tax Grouping")
        self._tabs.addTab(self._je_tree, "Journal Entries")

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
            self._populate_tax_grouping(self._last_bs, self._last_pl, self._last_group_map, gby, self._last_ties)
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

            # A line tied out to the return can go stale the moment the
            # trial balance changes underneath it -- catch that on every
            # rebuild (not just when the user happens to click the flag
            # again) by comparing each "reviewed" line's snapshotted value
            # against what it computes to right now, and downgrading it
            # back to "question" if they no longer match.
            current_values = _current_tie_values(bs, pl)
            invalidate_stale_ties(conn, self._job_id, current_values)
            ties = get_ties(conn, self._job_id)

        self._last_bs        = bs
        self._last_pl        = pl
        self._last_groups     = groups
        self._last_group_map  = group_map
        self._notes_by_account = notes_by_account
        self._tie_values      = current_values
        self._last_ties       = ties
        if job_row:
            self._client_name = job_row["client_name"] or ""
            self._entity_name = job_row["entity_name"] or ""
            self._tax_year    = job_row["tax_year"]    or 0

        gby = {g["group_id"]: g for g in groups}
        self._populate_bs(bs, pl, group_map, gby)
        self._populate_pl(pl, group_map, gby)
        self._populate_tax_grouping(bs, pl, group_map, gby, ties)
        self._populate_je()
        self._apply_cols()
        if self._collapsed:
            self._active_tree().collapseAll()

    # ── Column visibility ─────────────────────────────────────────────────

    def _apply_cols(self, *_):
        hidden_cols: set[int] = set()
        for cb, cols in self._group_checks:
            if cb.isChecked():
                hidden_cols.update(cols)
        for tree in (self._bs_tree, self._pl_tree, self._tax_tree):
            for c in range(1, _NCOLS):
                tree.setColumnHidden(c, c in hidden_cols)
            self._autofit_columns(tree, hidden_cols)

    @staticmethod
    def _autofit_columns(tree: QTreeWidget, hidden_cols: set[int]):
        """Size each visible column to its content. Without this, hiding a
        column group left the remaining visible columns at their old fixed
        width, either crowding together with leftover blank space at the
        end of the table or, for a column with wider values than its
        108px default, truncating them."""
        for c in range(1, _NCOLS):
            if c in hidden_cols:
                continue
            tree.resizeColumnToContents(c)
            min_w = 90 if c != _COL_NOTES else 110
            if tree.columnWidth(c) < min_w:
                tree.setColumnWidth(c, min_w)

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
            default_dir   = str(self._default_export_dir),
            visible_cols  = visible_cols,
            show_acct_num = self._show_acct_num,
        )
        if out:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Export Complete", f"Saved to:\n{out}")

    def _active_tree(self) -> QTreeWidget:
        return [self._bs_tree, self._pl_tree, self._tax_tree, self._je_tree][self._tabs.currentIndex()]

    # ── Tree factory ──────────────────────────────────────────────────────

    def _make_tree(self, tie_col: bool = False) -> QTreeWidget:
        """tie_col=True is the Tax Grouping tab only -- one extra trailing
        column (_COL_TIE) for the tie-out flag, with its own click-to-cycle
        handling and its own outline-drawing delegate."""
        ncols   = _TAX_NCOLS if tie_col else _NCOLS
        headers = _TAX_HEADERS if tie_col else _HEADERS
        tree = QTreeWidget()
        tree.setColumnCount(ncols)
        tree.setHeaderLabels(headers)
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
        tree.setItemDelegate(_TieBoxDelegate(tree) if tie_col else RoleBackgroundDelegate(tree))
        tree.setContextMenuPolicy(Qt.CustomContextMenu)
        tree.customContextMenuRequested.connect(
            lambda pos, t=tree: self._ctx_menu(t, pos)
        )
        if tie_col:
            tree.itemClicked.connect(self._on_tie_flag_clicked)
        hdr = tree.header()
        hdr.setSectionResizeMode(_COL_NAME, QHeaderView.Stretch)
        for c in range(1, _NCOLS):
            hdr.setSectionResizeMode(c, QHeaderView.Interactive)
            tree.setColumnWidth(c, 108 if c != _COL_NOTES else 130)
        if tie_col:
            hdr.setSectionResizeMode(_COL_TIE, QHeaderView.Fixed)
            tree.setColumnWidth(_COL_TIE, 70)
        hdr.setDefaultAlignment(Qt.AlignCenter)
        hdr.setStretchLastSection(False)
        hdr.setStyleSheet(
            f"QHeaderView::section {{"
            f"  background: {_TITLE_BG}; color: {_TITLE_FG};"
            f"  font-family: 'Segoe UI'; font-size: 11px; font-weight: bold;"
            f"  padding: 5px 8px; border: none; border-right: 1px solid #2A3B5C;"
            f"}}"
        )
        hdr.setContextMenuPolicy(Qt.CustomContextMenu)
        hdr.customContextMenuRequested.connect(
            lambda pos, t=tree: self._on_report_header_menu(t, pos)
        )
        return tree

    def _make_je_tree(self) -> QTreeWidget:
        """Separate, simpler layout from _make_tree() -- Entry #/Description/
        Account #/Account Name/DR/CR/Memo, column-for-column matching the
        exporter's Journal Entries Excel tab, rather than the 11-column
        financial-statement grid (PBC/AJE/ADJ/... has no meaning here)."""
        tree = QTreeWidget()
        tree.setColumnCount(_JE_NCOLS)
        tree.setHeaderLabels(_JE_HEADERS)
        tree.setRootIsDecorated(False)
        tree.setIndentation(0)
        tree.setAlternatingRowColors(False)
        tree.setSelectionBehavior(QTreeWidget.SelectRows)
        tree.setStyleSheet(_TREE_STYLE)
        tree.setItemDelegate(RoleBackgroundDelegate(tree))
        hdr = tree.header()
        hdr.setSectionResizeMode(_JE_COL_ENTRY, QHeaderView.Interactive)
        hdr.setSectionResizeMode(_JE_COL_DESC, QHeaderView.Stretch)
        hdr.setSectionResizeMode(_JE_COL_ACCTNUM, QHeaderView.Interactive)
        hdr.setSectionResizeMode(_JE_COL_ACCTNAME, QHeaderView.Stretch)
        for c in (_JE_COL_DR, _JE_COL_CR):
            hdr.setSectionResizeMode(c, QHeaderView.Interactive)
            tree.setColumnWidth(c, 110)
        hdr.setSectionResizeMode(_JE_COL_MEMO, QHeaderView.Stretch)
        tree.setColumnWidth(_JE_COL_ENTRY, 90)
        tree.setColumnWidth(_JE_COL_ACCTNUM, 80)
        hdr.setDefaultAlignment(Qt.AlignCenter)
        hdr.setStretchLastSection(False)
        hdr.setStyleSheet(
            f"QHeaderView::section {{"
            f"  background: {_TITLE_BG}; color: {_TITLE_FG};"
            f"  font-family: 'Segoe UI'; font-size: 11px; font-weight: bold;"
            f"  padding: 5px 8px; border: none; border-right: 1px solid #2A3B5C;"
            f"}}"
        )
        return tree

    def _populate_je(self):
        t = self._je_tree
        t.clear()
        self._write_title(t, "JOURNAL ENTRIES", ncols=_JE_NCOLS)

        with db_connection(self._path) as conn:
            entries = get_entries(conn, self._job_id)
            lines_by_entry = {e["aje_id"]: get_lines(conn, e["aje_id"]) for e in entries}

        if not entries:
            empty = QTreeWidgetItem([""] * _JE_NCOLS)
            empty.setFlags(Qt.ItemIsEnabled)
            empty.setText(_JE_COL_ENTRY, "No journal entries recorded.")
            empty.setForeground(_JE_COL_ENTRY, QBrush(QColor("#888888")))
            t.addTopLevelItem(empty)
            return

        by_type: dict[str, list[dict]] = {}
        for e in entries:
            by_type.setdefault(e["entry_type"], []).append(e)
        types_present = [ty for ty in _JE_TYPE_ORDER if by_type.get(ty)] + \
                        [ty for ty in by_type if ty not in _JE_TYPE_ORDER]

        grand_dr = grand_cr = 0.0
        for entry_type in types_present:
            type_entries = by_type[entry_type]
            type_dr = type_cr = 0.0
            _je_category(t, _JE_TYPE_LABELS.get(entry_type, entry_type))
            for e in type_entries:
                dr_total, cr_total = _je_entry(t, e, lines_by_entry[e["aje_id"]])
                type_dr += dr_total
                type_cr += cr_total
            _je_total_row(t, f"Total — {_JE_TYPE_LABELS.get(entry_type, entry_type)}",
                         type_dr, type_cr)
            _spacer(t, 10, _JE_NCOLS)
            grand_dr += type_dr
            grand_cr += type_cr

        _je_total_row(t, "GRAND TOTAL", grand_dr, grand_cr, heavy=True)

    def _on_report_header_menu(self, tree: QTreeWidget, pos):
        menu = QMenu(self)
        reset = menu.addAction("Auto-Fit Columns")
        if menu.exec(tree.header().mapToGlobal(pos)) == reset:
            hidden_cols = {c for c in range(1, _NCOLS) if tree.isColumnHidden(c)}
            self._autofit_columns(tree, hidden_cols)

    # ── Statement header (client / statement / period) ─────────────────────

    def _write_title(self, tree: QTreeWidget, statement_label: str, ncols: int = _NCOLS):
        """Centered 3-line title block -- same 3 rows and fills as
        review_package.py's _write_report_title: client name (navy fill,
        white bold), statement label (platinum fill, navy bold), period
        (no fill, navy italic).

        setFirstColumnSpanned(True) merges every column into one wide cell
        for this row — without it, "centering" only centers within the
        narrow Account Name column, not the full table width, which looks
        more off-center the more columns are visible.
        """
        period = f"Period ending: December 31, {self._tax_year}" if self._tax_year else ""
        name = self._client_name or self._entity_name
        for text, font_size, bold, italic, fg, bg in (
            (name,            13, True,  False, _TITLE_FG,  _TITLE_BG),
            (statement_label, 11, True,  False, _TITLE2_FG, _TITLE2_BG),
            (period,          10, False, True,  _NAVY,      None),
        ):
            item = QTreeWidgetItem([""] * ncols)
            item.setFlags(Qt.NoItemFlags)
            item.setText(0, text)
            item.setTextAlignment(0, Qt.AlignHCenter | Qt.AlignVCenter)
            f = QFont(); f.setPointSize(font_size); f.setBold(bold); f.setItalic(italic)
            item.setFont(0, f)
            item.setForeground(0, QBrush(QColor(fg)))
            if bg:
                for col in range(ncols):
                    item.setBackground(col, QBrush(QColor(bg)))
            tree.addTopLevelItem(item)
            item.setFirstColumnSpanned(True)
        _spacer(tree, 10, ncols)

    # ── Balance Sheet ─────────────────────────────────────────────────────

    def _write_balance_sheet_totals(self, t: QTreeWidget, r: FinancialReport,
                                    pl: FinancialReport | None, gmap: dict, gby: dict,
                                    section_writer, ncols: int = _NCOLS) -> float:
        """Shared by the Balance Sheet tab and the Balance Sheet portion of
        the Tax Grouping tab: writes ASSETS (with a Total Noncurrent Assets
        rollup + TOTAL ASSETS), then LIABILITIES & EQUITY (Total
        Liabilities, Current Year Net Income as its own equity line item,
        then Total Equity -- folding net income in so it isn't just
        tacked on after -- then TOTAL LIABILITIES & EQUITY). Returns the
        net income figure so callers needing a balance-check (the BS tab)
        can use it. `section_writer` is _section (plain, used by the BS
        tab) or a wrapper around _section_tax_grouping (with the tax-line
        tier and the tie-out flag column, used by Tax Grouping) so both
        tabs share one source of truth for this hierarchy instead of
        drifting apart. `ncols` must match whatever section_writer sizes
        its own rows for (_TAX_NCOLS for the tax-grouping wrapper)."""
        nba = self._notes_by_account
        san = self._show_acct_num

        _category(t, "ASSETS", ncols=ncols)
        noncurrent_asset_secs = []
        for sec in r.asset_sections:
            section_writer(t, sec, gmap, gby, nba, san)
            if _section_category(sec) != CATEGORY_CURRENT_ASSET:
                noncurrent_asset_secs.append(sec)
        # GAAP-style mid-level rollup (Fixed + Other Long-Term Assets), same
        # tier review_package.py's classified Balance Sheet Excel tab uses.
        if noncurrent_asset_secs:
            _mid_rollup(t, "Total Noncurrent Assets", noncurrent_asset_secs, ncols=ncols)
        _grand_total(t, "TOTAL ASSETS",
                     r.total_assets_pbc, r.total_assets_aje, r.total_assets_adj,
                     r.total_assets_rje, r.total_assets,
                     r.total_assets_ftje, r.total_assets_ftax,
                     r.total_assets_py_final, r.total_assets_py_ftax, ncols=ncols)
        _spacer(t, 16, ncols)

        _category(t, "LIABILITIES & EQUITY", ncols=ncols)
        # Two explicit passes -- liabilities (and anything not classified as
        # equity, conservatively treated as liability-like) always written
        # and subtotaled BEFORE equity, regardless of how the buckets happen
        # to sort in the DB, so "Total Liabilities" reads as the boundary
        # between the two, not a stray row after Stockholders' Equity.
        equity_secs    = [s for s in r.liability_equity_sections if _section_category(s) == CATEGORY_EQUITY]
        equity_ids     = {id(s) for s in equity_secs}
        liability_secs = [s for s in r.liability_equity_sections if id(s) not in equity_ids]
        for sec in liability_secs:
            section_writer(t, sec, gmap, gby, nba, san)
        if liability_secs:
            _mid_rollup(t, "Total Liabilities", liability_secs, ncols=ncols)
        for sec in equity_secs:
            section_writer(t, sec, gmap, gby, nba, san)

        # Current-year net income from P&L — carries into equity for balance
        # check. A working TB has income/expense mapped to P&L, so equity
        # only has the prior-period balance; net income is injected here,
        # as its OWN equity line item (not tacked on after Total Equity),
        # and folded into that Total Equity subtotal below so the two
        # numbers stay consistent with each other.
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

        if equity_secs:
            _mid_rollup_values(
                t, "Total Equity",
                sum(s.subtotal_pbc      for s in equity_secs) + ni_pbc,
                sum(s.subtotal_aje      for s in equity_secs) + ni_aje,
                sum(s.subtotal_adj      for s in equity_secs) + ni_adj,
                sum(s.subtotal_rje      for s in equity_secs) + ni_rje,
                sum(s.subtotal          for s in equity_secs) + ni,
                sum(s.subtotal_ftje     for s in equity_secs) + ni_ftje,
                sum(s.subtotal_ftax     for s in equity_secs) + ni_ftax,
                sum(s.subtotal_py_final for s in equity_secs) + ni_pyf,
                sum(s.subtotal_py_ftax  for s in equity_secs) + ni_pyx,
                ncols=ncols,
            )

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
                     r.total_liabilities_equity_py_ftax  + ni_pyx, ncols=ncols)
        _spacer(t, 8, ncols)
        return ni

    def _populate_bs(self, r: FinancialReport, pl: FinancialReport | None,
                     gmap: dict, gby: dict):
        t = self._bs_tree
        t.clear()
        self._write_title(t, "BALANCE SHEET")

        ni = self._write_balance_sheet_totals(t, r, pl, gmap, gby, _section)

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

    # ── Tax Grouping ─────────────────────────────────────────────────────
    # Same accounts as the BS/PL tabs above, but organized by tax line
    # across BOTH statements in one pass -- mirrors the "Tax Grouping" tab
    # already produced in the exported .bta.xlsx package (see
    # exporter/review_package.py:_write_tax_grouping_tab), so preparers get
    # that same view without leaving the app.

    def _populate_tax_grouping(self, bs: FinancialReport, pl: FinancialReport,
                               gmap: dict, gby: dict, ties: dict):
        t = self._tax_tree
        t.clear()
        self._write_title(t, "TAX GROUPING", ncols=_TAX_NCOLS)
        nba = self._notes_by_account
        san = self._show_acct_num

        def section_writer(tree, sec, gmap, gby, nba, san):
            _section_tax_grouping(tree, sec, gmap, gby, nba, san, ties=ties)

        # Same TOTAL ASSETS / Total Liabilities / Total Equity (net income
        # folded in) / TOTAL LIABILITIES & EQUITY hierarchy as the Balance
        # Sheet tab -- this view previously had none of those, just a bare
        # list of buckets with net income tacked on at the end.
        self._write_balance_sheet_totals(t, bs, pl, gmap, gby, section_writer, ncols=_TAX_NCOLS)
        _spacer(t, 8, _TAX_NCOLS)

        _category(t, "PROFIT & LOSS", ncols=_TAX_NCOLS)
        drd_sec = next((s for s in pl.sections if s.name == "Dividends Received Deduction"), None)
        for sec in pl.sections:
            section_writer(t, sec, gmap, gby, nba, san)
            # C-corps only (drd_sec is only ever present for 1120): the DRD
            # is computed on income AFTER the NOL is absorbed, so this
            # intermediate total belongs between the two -- it's simply the
            # final net income figure with the not-yet-applied DRD bucket
            # added back in.
            if sec.name == "Net Operating Loss Deduction" and drd_sec is not None:
                _mid_rollup_values(
                    t, "Income after Net Operating Loss Deduction",
                    pl.net_income_pbc      + drd_sec.subtotal_pbc,
                    pl.net_income_aje      + drd_sec.subtotal_aje,
                    pl.net_income_adj      + drd_sec.subtotal_adj,
                    pl.net_income_rje      + drd_sec.subtotal_rje,
                    pl.net_income          + drd_sec.subtotal,
                    pl.net_income_ftje     + drd_sec.subtotal_ftje,
                    pl.net_income_ftax     + drd_sec.subtotal_ftax,
                    pl.net_income_py_final + drd_sec.subtotal_py_final,
                    pl.net_income_py_ftax  + drd_sec.subtotal_py_ftax,
                    ncols=_TAX_NCOLS,
                )
        _grand_total(t, "NET INCOME / (LOSS)",
                     pl.net_income_pbc, pl.net_income_aje, pl.net_income_adj,
                     pl.net_income_rje, pl.net_income,
                     pl.net_income_ftje, pl.net_income_ftax,
                     pl.net_income_py_final, pl.net_income_py_ftax, ncols=_TAX_NCOLS)

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

    def _on_tie_flag_clicked(self, item: QTreeWidgetItem, column: int):
        """Tax Grouping tab only: clicking the tie-out box toggles it
        blank <-> checked (a stale/flagged line is re-confirmed straight to
        checked). Stored in a completely separate table (tax_grouping_ties)
        from the Trial Balance's own flags -- see cycle_tie_flag()'s
        docstring for why the two are deliberately never linked."""
        if column != _COL_TIE:
            return
        account_id = item.data(0, Qt.UserRole)
        if not account_id:
            return
        current_value = self._tie_values.get(account_id)
        with db_connection(self._path) as conn:
            cycle_tie_flag(conn, self._job_id, account_id, current_value, self._performed_by)
        self.reprint()


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


def _current_tie_values(bs: FinancialReport, pl: FinancialReport) -> dict[str, float]:
    """The value each account's tie-out flag should be checked/snapshotted
    against: FINAL for Balance Sheet lines, FTAX for P&L lines -- the two
    different "what actually goes on the return" columns per statement
    type. Used both when a line is newly marked tied-out and, every time
    the report rebuilds, to detect that the trial balance moved since."""
    values: dict[str, float] = {}
    for sec in bs.sections:
        for ln in sec.lines:
            values[ln.account_id] = ln.display_final
    for sec in pl.sections:
        for ln in sec.lines:
            values[ln.account_id] = ln.display_ftax
    return values


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


def _category(tree: QTreeWidget, label: str, ncols: int = _NCOLS):
    item = QTreeWidgetItem([""] * ncols)
    item.setFlags(Qt.ItemIsEnabled)
    item.setText(_COL_NAME, _indent(label, 0))
    item.setFont(_COL_NAME, _bold())
    for col in range(ncols):
        item.setBackground(col, QBrush(QColor(_CATEGORY_BG)))
        item.setForeground(col, QBrush(QColor(_CATEGORY_FG)))
    item.setTextAlignment(_COL_NAME, Qt.AlignLeft | Qt.AlignVCenter)
    tree.addTopLevelItem(item)


def _je_category(tree: QTreeWidget, label: str):
    """FS/entry-type banner row -- same black-fill/white-text treatment as
    review_package.py's AJE/RJE/FTJE block headers in the Journal Entries
    Excel tab."""
    item = QTreeWidgetItem([""] * _JE_NCOLS)
    item.setFlags(Qt.ItemIsEnabled)
    item.setText(_JE_COL_ENTRY, label)
    item.setFont(_JE_COL_ENTRY, _bold())
    for col in range(_JE_NCOLS):
        item.setBackground(col, QBrush(QColor(_CATEGORY_BG)))
        item.setForeground(col, QBrush(QColor(_CATEGORY_FG)))
    item.setTextAlignment(_JE_COL_ENTRY, Qt.AlignLeft | Qt.AlignVCenter)
    tree.addTopLevelItem(item)


def _je_entry(tree: QTreeWidget, entry: dict, lines: list[dict]) -> tuple[float, float]:
    """Write one journal entry as flat rows -- Entry #/Description carried
    only on the first line, one row per line item, closed out with its own
    platinum DR/CR subtotal row. Mirrors _write_journal_entries_tab in
    review_package.py column-for-column (Entry # | Description | Account # |
    Account Name | DR | CR | Memo) rather than a nested nested-tree layout,
    since that flat layout is what preparers already read off the Excel
    export. Returns (dr_total, cr_total)."""
    is_balanced = bool(entry.get("is_balanced"))

    dr_total = cr_total = 0.0
    for i, ln in enumerate(lines):
        row = QTreeWidgetItem([""] * _JE_NCOLS)
        row.setFlags(Qt.ItemIsEnabled)
        if i == 0:
            row.setText(_JE_COL_ENTRY, entry["entry_number"])
            row.setText(_JE_COL_DESC, entry["description"])
        row.setText(_JE_COL_ACCTNUM, ln.get("account_number") or "")
        row.setText(_JE_COL_ACCTNAME, ln.get("account_name") or "")
        amt = ln["amount"]
        row.setText(_JE_COL_DR, _fmt(amt) if amt > 0 else "—")
        row.setText(_JE_COL_CR, _fmt(abs(amt)) if amt < 0 else "—")
        if amt > 0:
            dr_total += amt
        elif amt < 0:
            cr_total += abs(amt)
        for col in (_JE_COL_DR, _JE_COL_CR):
            row.setFont(col, _mono())
            row.setTextAlignment(col, Qt.AlignRight | Qt.AlignVCenter)
        memo = ln.get("memo") or ""
        if memo:
            row.setText(_JE_COL_MEMO, memo)
            f = QFont(); f.setItalic(True)
            row.setFont(_JE_COL_MEMO, f)
            row.setForeground(_JE_COL_MEMO, QBrush(QColor("#666666")))
        if i == 0:
            # Medium top rule separates one entry from the next, same as the
            # exporter's Border(top=Side(style="medium", ...)) on an entry's
            # first line.
            _rule(tree, heavy=True, ncols=_JE_NCOLS)
        tree.addTopLevelItem(row)

    if not is_balanced:
        warn = QTreeWidgetItem([""] * _JE_NCOLS)
        warn.setFlags(Qt.ItemIsEnabled)
        warn.setText(_JE_COL_ENTRY, "✗ UNBALANCED")
        warn.setForeground(_JE_COL_ENTRY, QBrush(QColor("#7B1A1A")))
        f = QFont(); f.setBold(True)
        warn.setFont(_JE_COL_ENTRY, f)
        tree.addTopLevelItem(warn)

    sub = QTreeWidgetItem([""] * _JE_NCOLS)
    sub.setFlags(Qt.ItemIsEnabled)
    sub.setText(_JE_COL_ACCTNAME, f"Entry {entry['entry_number']} Total")
    sub.setFont(_JE_COL_ACCTNAME, _bold())
    sub.setText(_JE_COL_DR, _fmt(dr_total))
    sub.setText(_JE_COL_CR, _fmt(cr_total))
    for col in range(_JE_NCOLS):
        sub.setBackground(col, QBrush(QColor(_SUBTOTAL_BG)))
        sub.setForeground(col, QBrush(QColor(_SUBTOTAL_FG)))
    for col in (_JE_COL_DR, _JE_COL_CR):
        sub.setFont(col, _mono(bold=True))
        sub.setTextAlignment(col, Qt.AlignRight | Qt.AlignVCenter)
    tree.addTopLevelItem(sub)
    _spacer(tree, 6, _JE_NCOLS)
    return dr_total, cr_total


def _je_total_row(tree: QTreeWidget, label: str, dr_total: float, cr_total: float, heavy: bool = False):
    """Type-level ('Total — Adjusting Journal Entries') or grand ('GRAND
    TOTAL') subtotal row -- same platinum styling as an entry's own
    subtotal, matching review_package.py's uniform _write_total_row tier."""
    item = QTreeWidgetItem([""] * _JE_NCOLS)
    item.setFlags(Qt.ItemIsEnabled)
    item.setText(_JE_COL_ACCTNAME, label)
    item.setFont(_JE_COL_ACCTNAME, _bold())
    item.setText(_JE_COL_DR, _fmt(dr_total))
    item.setText(_JE_COL_CR, _fmt(cr_total))
    for col in range(_JE_NCOLS):
        item.setBackground(col, QBrush(QColor(_GRANDTOTAL_BG if heavy else _SUBTOTAL_BG)))
        item.setForeground(col, QBrush(QColor(_GRANDTOTAL_FG if heavy else _SUBTOTAL_FG)))
    for col in (_JE_COL_DR, _JE_COL_CR):
        item.setFont(col, _mono(bold=True))
        item.setTextAlignment(col, Qt.AlignRight | Qt.AlignVCenter)
    _rule(tree, heavy=heavy, ncols=_JE_NCOLS)
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


def _write_bucket_header(tree: QTreeWidget, name: str, ncols: int = _NCOLS) -> QTreeWidgetItem:
    hdr = QTreeWidgetItem([""] * ncols)
    hdr.setFlags(Qt.ItemIsEnabled)
    hdr.setText(_COL_NAME, _indent(name, 0))
    hdr.setFont(_COL_NAME, _bold())
    for col in range(ncols):
        hdr.setBackground(col, QBrush(QColor(_BUCKET_BG)))
        hdr.setForeground(col, QBrush(QColor(_BUCKET_FG)))
    hdr.setTextAlignment(_COL_NAME, Qt.AlignLeft | Qt.AlignVCenter)
    tree.addTopLevelItem(hdr)
    return hdr


def _write_bucket_subtotal(tree: QTreeWidget, name: str, sec: ReportSection, ncols: int = _NCOLS):
    """Bucket subtotal — bold, platinum-shaded (matches review_package.py's
    _write_total_row tier), thin top border. This is the ONLY subtotal tier
    review_package.py's Tax Grouping/Trial Balance tabs ever draw (no
    separate per-tax-line subtotal) — the previous version of this function
    accidentally stopped calling this entirely (dead code left after an
    unrelated helper's `return`), which is why bucket subtotals silently
    vanished from every report-tab view."""
    sub = _make_item(_indent(f"Total {name}", 0), _vals(sec))
    sub.setFlags(Qt.ItemIsEnabled)
    sub.setFont(_COL_NAME, _bold())
    sub.setTextAlignment(_COL_NAME, Qt.AlignLeft | Qt.AlignVCenter)
    _style_num_cols(sub, bold=True)
    for col in range(ncols):
        sub.setBackground(col, QBrush(QColor(_SUBTOTAL_BG)))
    sub.setForeground(_COL_NAME, QBrush(QColor(_SUBTOTAL_FG)))
    _rule(tree, ncols=ncols)
    tree.addTopLevelItem(sub)
    _spacer(tree, 6, ncols)


def _split_groups(lines: list[ReportLine], gmap: dict, gby: dict):
    """Split a flat list of ReportLines into (grouped-by-gid, ungrouped)."""
    grouped: dict[str, list[ReportLine]] = {}
    ungrouped: list[ReportLine] = []
    for ln in lines:
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
    return grouped, ungrouped, all_gids, root_gids


def _section(tree: QTreeWidget, sec: ReportSection, gmap: dict, gby: dict,
            notes_by_account: dict, show_acct_num: bool = True):
    """Balance Sheet / P&L tabs: bucket header (e.g. "Current Assets") with
    its accounts/custom-groups listed flat underneath -- approximates a
    GAAP/QBO-style classified statement. No individual-tax-line breakout
    here on purpose: that finer tier (which ties to the tax return) belongs
    only on the Tax Grouping tab -- see _section_tax_grouping()."""
    name = _display_section_name(sec)
    hdr = _write_bucket_header(tree, name)

    grouped, ungrouped, all_gids, root_gids = _split_groups(sec.lines, gmap, gby)
    for gid in root_gids:
        _group_node(hdr, gid, gby, grouped, all_gids, notes_by_account, level=1, show_acct_num=show_acct_num)
    for ln in ungrouped:
        _acct(hdr, ln, notes_by_account, level=1, show_acct_num=show_acct_num)
    hdr.setExpanded(True)

    _write_bucket_subtotal(tree, name, sec)


def _section_tax_grouping(tree: QTreeWidget, sec: ReportSection, gmap: dict, gby: dict,
                          notes_by_account: dict, show_acct_num: bool = True,
                          ties: dict | None = None):
    """Tax Grouping tab only: same bucket header/subtotal as _section(), but
    with the individual tax line (e.g. "Cash", carried on
    ReportLine.line_name) shown as its own row between the bucket and its
    accounts -- ties this tab to the tax return, matching the .bta Excel
    export's Tax Grouping tab column-for-column. Accounts/groups/tax-line
    rows all become real CHILDREN of the bucket header (so Collapse All /
    Expand All actually hides them), while the subtotal stays a top-level
    sibling -- it's still visible even when the bucket is collapsed.

    `ties` (account_id -> {flag, tied_value, ...}) is only passed on this
    tab, which is what also tells every nested row-builder here to size
    itself for the extra tie-out-flag column (_TAX_NCOLS) instead of the
    plain _NCOLS the Balance Sheet/P&L tabs use.
    """
    ncols = _TAX_NCOLS if ties is not None else _NCOLS
    name = _display_section_name(sec)
    hdr = _write_bucket_header(tree, name, ncols=ncols)

    # Sub-group by tax line, preserving first-seen order -- the SQL in
    # builder.py already orders by (section_sort_order, tax line's own
    # sort_order), so each tax line's accounts arrive contiguously.
    line_order: list[str] = []
    lines_by_tax_line: dict[str, list[ReportLine]] = {}
    for ln in sec.lines:
        key = ln.line_name or "Unmapped"
        if key not in lines_by_tax_line:
            line_order.append(key)
            lines_by_tax_line[key] = []
        lines_by_tax_line[key].append(ln)

    for tax_line_name in line_order:
        tl_lines = lines_by_tax_line[tax_line_name]
        tl_item = _tax_line_row(hdr, tax_line_name, level=1, ncols=ncols)

        # Custom account groups are an app-only feature the Excel export
        # doesn't have, scoped to a single tax line here, same as the app
        # already constrains them to one tax line elsewhere.
        grouped, ungrouped, all_gids, root_gids = _split_groups(tl_lines, gmap, gby)
        for gid in root_gids:
            _group_node(tl_item, gid, gby, grouped, all_gids, notes_by_account, level=2,
                       show_acct_num=show_acct_num, ties=ties)
        for ln in ungrouped:
            _acct(tl_item, ln, notes_by_account, level=2, show_acct_num=show_acct_num, ties=ties)
    hdr.setExpanded(True)

    _write_bucket_subtotal(tree, name, sec, ncols=ncols)


def _tax_line_row(parent, label: str, level: int, ncols: int = _NCOLS) -> QTreeWidgetItem:
    """Tax-line subheader (e.g. "Cash") between a bucket header and its
    accounts -- light blue / navy, NOT bold, matching review_package.py's
    _write_section_row(f"  {line_name}", bg=_LIGHT, fg=_NAVY, bold=False).
    No subtotal at this tier: the exporter only subtotals at the bucket
    level, so this file doesn't invent one either."""
    item = QTreeWidgetItem([""] * ncols)
    item.setFlags(Qt.ItemIsEnabled)
    item.setText(_COL_NAME, _indent(label, level))
    for col in range(ncols):
        item.setBackground(col, QBrush(QColor(_TAXLINE_BG)))
        item.setForeground(col, QBrush(QColor(_TAXLINE_FG)))
    item.setTextAlignment(_COL_NAME, Qt.AlignLeft | Qt.AlignVCenter)
    _add_item(parent, item)
    item.setExpanded(True)
    return item


def _group_node(parent, gid: str, gby: dict,
                grouped: dict, all_gids: set, notes_by_account: dict, level: int,
                show_acct_num: bool = True, ties: dict | None = None):
    group = gby.get(gid)
    if not group:
        return
    lines = _collect(gid, gby, grouped, all_gids)
    if not lines:
        return

    ncols = _TAX_NCOLS if ties is not None else _NCOLS
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
    for col in range(ncols):
        g_item.setBackground(col, QBrush(QColor(_GROUP_BG)))
    g_item.setForeground(_COL_NAME, QBrush(QColor(_GROUP_FG)))
    _add_item(parent, g_item)

    child_gids = sorted(
        [g for g in all_gids if gby.get(g, {}).get("parent_id") == gid],
        key=lambda g: gby.get(g, {}).get("sort_order", 0),
    )
    for cid in child_gids:
        _group_node(g_item, cid, gby, grouped, all_gids, notes_by_account, level=level + 1,
                   show_acct_num=show_acct_num, ties=ties)
    for ln in grouped.get(gid, []):
        _acct(g_item, ln, notes_by_account, level=level + 1, show_acct_num=show_acct_num, ties=ties)

    # Subtotal at the bottom of the group (GAAP style) — a real child of the
    # group, so it (unlike the section-level subtotal) hides along with the
    # rest of the group when collapsed.
    sub = _make_item(_indent(f"Total {group['name']}", level), dv)
    sub.setFlags(Qt.ItemIsEnabled)
    sub.setFont(_COL_NAME, _bold())
    sub.setTextAlignment(_COL_NAME, Qt.AlignLeft | Qt.AlignVCenter)
    _style_num_cols(sub, bold=True)
    for col in range(ncols):
        sub.setBackground(col, QBrush(QColor(_SUBTOTAL_BG)))
    sub.setForeground(_COL_NAME, QBrush(QColor(_SUBTOTAL_FG)))
    _rule(g_item, ncols=ncols)
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
         show_acct_num: bool = True, ties: dict | None = None):
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
    # Plain black text, matching the exporter's data rows -- account names
    # only get color when they need to flag something (open notes).
    if ln.has_open_notes:
        item.setForeground(_COL_NAME, QBrush(QColor(_NOTE_FG)))
    _style_num_cols(item, bold=False)
    item.setData(0, Qt.UserRole, ln.account_id)
    item.setData(0, Qt.UserRole + 1, ln.account_name)
    _write_notes_cell(item, ln, notes_by_account)
    if ties is not None:
        _write_tie_cell(item, ln, ties)
    _add_item(parent, item)


def _write_tie_cell(item: QTreeWidgetItem, ln: ReportLine, ties: dict):
    """Tax Grouping tab only: the tie-out flag box -- a preparer's own
    "entered on the return and tied out" mark, cycled by clicking (see
    ReportTab._on_tie_flag_clicked), completely independent of
    ln.flag/the Trial Balance's account flag."""
    tie = ties.get(ln.account_id) or {}
    flag = tie.get("flag")
    symbol, color = _TIE_FLAG_DISPLAY.get(flag, ("", "#6B7280"))
    item.setBackground(_COL_TIE, QBrush(QColor(_TIE_BOX_BG)))
    item.setText(_COL_TIE, symbol)
    item.setForeground(_COL_TIE, QBrush(QColor(color)))
    item.setTextAlignment(_COL_TIE, Qt.AlignCenter | Qt.AlignVCenter)
    f = QFont(); f.setPointSize(f.pointSize() + 2); f.setBold(True)
    item.setFont(_COL_TIE, f)
    tooltip = {
        None:       "Click to mark this line entered on the return and tied out.",
        "question": "The trial balance changed since this was tied out -- "
                    "click to re-confirm against the current amount.",
        "reviewed": f"Tied out{' by ' + tie['tied_by'] if tie.get('tied_by') else ''}"
                    f"{' on ' + tie['tied_at'][:10] if tie.get('tied_at') else ''}. "
                    "Click to clear.",
    }[flag]
    item.setToolTip(_COL_TIE, tooltip)


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


def _mid_rollup(tree: QTreeWidget, label: str, sections: list[ReportSection], ncols: int = _NCOLS):
    """Roll several buckets together into one subtotal (e.g. Fixed Assets +
    Other Long-Term Assets -> Total Noncurrent Assets) -- same platinum
    subtotal tier as a single bucket's own total, matching the mid-level
    rollups in review_package.py's classified Balance Sheet Excel tab."""
    def total(attr: str) -> float:
        return sum(getattr(s, attr) for s in sections)

    _mid_rollup_values(
        tree, label,
        total("subtotal_pbc"), total("subtotal_aje"), total("subtotal_adj"),
        total("subtotal_rje"), total("subtotal"),
        total("subtotal_ftje"), total("subtotal_ftax"),
        total("subtotal_py_final"), total("subtotal_py_ftax"),
        ncols=ncols,
    )


def _mid_rollup_values(tree: QTreeWidget, label: str,
                       pbc: float, aje: float, adj: float,
                       rje: float, final: float,
                       ftje: float, ftax: float,
                       py_final: float = 0.0, py_ftax: float = 0.0,
                       ncols: int = _NCOLS):
    """Same platinum subtotal tier as _mid_rollup(), but from already-summed
    values rather than a list of ReportSections -- needed for "Total Equity"
    once Current Year Net Income (a synthetic line, not a real
    ReportSection) has to be folded into it."""
    dv = [_fmt(pbc), _fmt(aje), _fmt(adj), _fmt(rje), _fmt(final),
          _fmt(ftje), _fmt(ftax), _fmt(py_final), _fmt(py_ftax)]
    item = _make_item(_indent(label, 0), dv)
    item.setFlags(Qt.ItemIsEnabled)
    item.setFont(_COL_NAME, _bold())
    item.setTextAlignment(_COL_NAME, Qt.AlignLeft | Qt.AlignVCenter)
    _style_num_cols(item, bold=True)
    for col in range(ncols):
        item.setBackground(col, QBrush(QColor(_SUBTOTAL_BG)))
    item.setForeground(_COL_NAME, QBrush(QColor(_SUBTOTAL_FG)))
    _rule(tree, ncols=ncols)
    tree.addTopLevelItem(item)
    _spacer(tree, 8, ncols)


def _grand_total(tree: QTreeWidget, label: str,
                 pbc: float, aje: float, adj: float,
                 rje: float, final: float,
                 ftje: float, ftax: float,
                 py_final: float = 0.0, py_ftax: float = 0.0,
                 ncols: int = _NCOLS):
    dv = [_fmt(pbc), _fmt(aje), _fmt(adj), _fmt(rje), _fmt(final),
          _fmt(ftje), _fmt(ftax), _fmt(py_final), _fmt(py_ftax)]
    item = _make_item(_indent(label, 0), dv)
    item.setFlags(Qt.ItemIsEnabled)
    item.setFont(_COL_NAME, _bold())
    item.setTextAlignment(_COL_NAME, Qt.AlignLeft | Qt.AlignVCenter)
    _style_num_cols(item, bold=True)
    for col in range(ncols):
        item.setBackground(col, QBrush(QColor(_GRANDTOTAL_BG)))
        item.setForeground(col, QBrush(QColor(_GRANDTOTAL_FG)))
    _rule(tree, heavy=True, ncols=ncols)
    tree.addTopLevelItem(item)


def _rule(parent, heavy: bool = False, ncols: int = _NCOLS):
    """A hairline row — QTreeWidgetItem has no per-item border property, so
    a top border is drawn as a thin filled row immediately above the total
    it belongs to. `heavy` is used for grand totals (Total Assets, Total
    Liabilities & Equity, Net Income) so they read as more final than an
    ordinary section subtotal. `parent` is the QTreeWidget for a top-level
    rule, or a QTreeWidgetItem to nest the rule as a real child (e.g. right
    before a group's own subtotal, so it collapses along with the group)."""
    item = QTreeWidgetItem([""] * ncols)
    item.setFlags(Qt.NoItemFlags)
    clr = QColor(_RULE_HEAVY if heavy else _RULE_LIGHT)
    height = QSize(0, 2 if heavy else 1)
    for col in range(ncols):
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


def _spacer(parent, h: int = 6, ncols: int = _NCOLS):
    item = QTreeWidgetItem([""] * ncols)
    item.setFlags(Qt.NoItemFlags)
    size = QSize(0, h)
    for col in range(ncols):
        item.setData(col, Qt.SizeHintRole, size)
    _add_item(parent, item)
