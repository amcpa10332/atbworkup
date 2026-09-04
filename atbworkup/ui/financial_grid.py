"""
Financial statement grid widget.

Columns: [✓ checkbox] [⚑ flag] [Acct #] [Account Name]
         [PBC] [AJE] [ADJ] [RJE] [FINAL] [FTJE] [FTAX]

Sign convention: DR = positive (black), CR = negative shown as (1,234.56) in red.
Section header rows show column subtotals.
Read-only at M3; editing wired in M5.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QFrame,
    QTreeWidget, QTreeWidgetItem, QTreeWidgetItemIterator,
    QHeaderView, QMenu, QPushButton,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QBrush

from atbworkup.db.connection import db_connection
from atbworkup.models.accounts import get_grouped_balances, set_flag, delete_accounts
from atbworkup.models.groups import get_groups, get_group_members
from atbworkup.ui.theme import (
    SECTION_BG, SECTION_FG, SUBSECTION_BG, SUBSECTION_FG,
    UNMAPPED_BG, UNMAPPED_FG,
    ROW_BG_ODD, ROW_BG_EVEN,
    TEXT_PRIMARY, TEXT_MUTED, TEXT_CREDIT,
    COL_HEADER_BG, COL_HEADER_FG,
    SELECTION_BG, SELECTION_FG,
    WARN_BADGE_BG, WARN_BADGE_FG,
    fmt_amount,
)

# ── Column indices ───────────────────────────────────────────────────────
COL_CHECK  = 0
COL_FLAG   = 1
COL_NUM    = 2
COL_NAME   = 3
COL_PBC    = 4
COL_AJE    = 5
COL_ADJ    = 6
COL_RJE    = 7
COL_FINAL  = 8
COL_FTJE   = 9
COL_FTAX   = 10

HEADERS = ["", "⚑", "Acct #", "Account Name",
           "PBC", "AJE", "ADJ", "RJE", "FINAL", "FTJE", "FTAX"]

_AMOUNT_COLS = [COL_PBC, COL_AJE, COL_ADJ, COL_RJE, COL_FINAL, COL_FTJE, COL_FTAX]
_AMOUNT_KEYS = ["pbc_balance", "aje", "adj", "rje", "final", "ftje", "ftax"]

# Flag cycle: None → flag (⚑) → check (✓) → X (✗) → None
_FLAG_CYCLE = [None, "question", "reviewed", "issue"]
_FLAG_DISPLAY = {
    "question": ("⚑", QColor("#f9a825")),
    "reviewed": ("✓", QColor("#2e7d32")),
    "issue":    ("✗", QColor("#c62828")),
    None:       ("",  QColor("transparent")),
}

_FS_LABELS = {
    "BalanceSheet":  "Balance Sheet",
    "ProfitAndLoss": "Profit & Loss",
    "Unmapped":      "⚠  Unmapped Accounts",
}
_FS_ORDER = ["BalanceSheet", "ProfitAndLoss", "Unmapped"]

_GRID_STYLE = f"""
QTreeWidget {{
    background-color: #FFFFFF;
    color: #000000;
    gridline-color: #EDEDED;
    alternate-background-color: #F7F8FA;
    font-family: "Segoe UI";
    font-size: 13px;
    border: 1px solid #E5E5E5;
    border-bottom: none;
    outline: none;
}}
QTreeWidget::item {{
    padding: 4px 2px;
    border-bottom: 1px solid #F2F2F2;
}}
QTreeWidget::item:hover {{
    background-color: #F0F4FA;
}}
QTreeWidget::item:selected {{
    background-color: {SELECTION_BG.name()};
    color: #000000;
}}
QHeaderView::section {{
    background-color: {COL_HEADER_BG.name()};
    color: #FFFFFF;
    font-family: "Segoe UI";
    font-size: 11px;
    font-weight: bold;
    letter-spacing: 1px;
    padding: 7px 6px;
    border: none;
    border-right: 1px solid #2A3B5C;
}}
"""

_TOTALS_STYLE = f"""
QTreeWidget {{
    background-color: {COL_HEADER_BG.name()};
    color: #FFFFFF;
    font-family: "Segoe UI";
    font-size: 12px;
    font-weight: bold;
    border: 1px solid #0f1d33;
    border-top: 3px double #FFFFFF;
}}
QTreeWidget::item {{
    padding: 5px 2px;
    background-color: {COL_HEADER_BG.name()};
    color: #FFFFFF;
    border: none;
}}
QScrollBar:horizontal {{ height: 0px; }}
"""

_TOOLBAR_CARD_STYLE = "background: #F7F7F7; border-bottom: 1px solid #E0E0E0;"
_COLBAR_CARD_STYLE  = "background: #FBFBFC; border-bottom: 1px solid #E5E5E5;"


class FinancialGrid(QWidget):
    """The main trial balance grid."""

    selection_changed = Signal(list)   # list of selected account_ids
    je_requested      = Signal(str, str)   # (account_id, entry_type)
    note_requested    = Signal(str, str)   # (account_id, account_name)
    account_created   = Signal()           # emitted after a new account is added

    def __init__(self, path: str | Path, job_id: str, entity_type: str,
                 performed_by: str, parent=None):
        super().__init__(parent)
        self._path = Path(path)
        self._job_id = job_id
        self._entity_type = entity_type
        self._performed_by = performed_by
        self._reviewer_note_ids: set = set()
        self._build_ui()
        self.refresh()

    # ── Build ────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # toolbar
        toolbar_card = QFrame()
        toolbar_card.setStyleSheet(_TOOLBAR_CARD_STYLE)
        toolbar = QHBoxLayout(toolbar_card)
        toolbar.setContentsMargins(10, 6, 10, 6)
        toolbar.setSpacing(8)

        self._unmapped_badge = QLabel()
        self._unmapped_badge.setStyleSheet(
            f"color: {WARN_BADGE_FG.name()}; background: {WARN_BADGE_BG.name()};"
            "padding: 4px 12px; border-radius: 10px; font-weight: bold; font-size: 11px; cursor: pointer;"
        )
        self._unmapped_badge.setVisible(False)
        self._unmapped_badge.setCursor(Qt.PointingHandCursor)
        self._unmapped_badge.mousePressEvent = lambda _e: self._open_mapping_workbench()

        btn_new_acct = QPushButton("+ New Account…")
        btn_new_acct.setStyleSheet(
            "QPushButton { font-size: 11px; font-weight: bold; padding: 4px 12px; "
            "border: 1px solid #1A2B4C; border-radius: 4px; background: #FFFFFF; color: #1A2B4C; }"
            "QPushButton:hover { background: #E4EEFB; }"
            "QPushButton:pressed { background: #D0E0F5; }"
        )
        btn_new_acct.clicked.connect(self._on_new_account)

        toolbar.addWidget(self._unmapped_badge)
        toolbar.addStretch()
        toolbar.addWidget(btn_new_acct)
        layout.addWidget(toolbar_card)

        # Column visibility toggles
        colbar_card = QFrame()
        colbar_card.setStyleSheet(_COLBAR_CARD_STYLE)
        col_bar = QHBoxLayout(colbar_card)
        col_bar.setContentsMargins(10, 5, 10, 5)
        col_bar.setSpacing(10)
        _sep_lbl = QLabel("SHOW COLUMNS")
        _sep_lbl.setStyleSheet(
            "color: #8A93A5; font-size: 10px; font-weight: bold; letter-spacing: 1px; padding-right: 4px;"
        )
        col_bar.addWidget(_sep_lbl)

        _CB_STYLE = "font-size: 11px; color: #333; spacing: 4px;"
        self._col_checks: list[tuple[QCheckBox, int]] = []

        # Every non-fixed column is toggleable.
        # Separators visually group: identity | working cols | finalisation cols
        _cols = [
            ("Acct #", COL_NUM,   None),
            ("PBC",    COL_PBC,   None),
            ("AJE",    COL_AJE,   None),
            ("ADJ",    COL_ADJ,   "after"),   # separator after ADJ
            ("RJE",    COL_RJE,   None),
            ("Final",  COL_FINAL, None),
            ("FTJE",   COL_FTJE,  None),
            ("FTax",   COL_FTAX,  None),
        ]
        for label, col, sep_pos in _cols:
            cb = QCheckBox(label)
            cb.setChecked(True)
            cb.setStyleSheet(_CB_STYLE)
            cb.toggled.connect(self._apply_col_visibility)
            col_bar.addWidget(cb)
            self._col_checks.append((cb, col))
            if sep_pos == "after":
                vsep = QFrame()
                vsep.setFrameShape(QFrame.VLine)
                vsep.setStyleSheet("color: #CCC;")
                col_bar.addWidget(vsep)

        col_bar.addStretch()
        layout.addWidget(colbar_card)

        # tree widget
        self._tree = QTreeWidget()
        self._tree.setColumnCount(len(HEADERS))
        self._tree.setHeaderLabels(HEADERS)
        self._tree.setRootIsDecorated(True)
        self._tree.setIndentation(20)
        self._tree.setUniformRowHeights(True)
        self._tree.setSelectionMode(QTreeWidget.ExtendedSelection)
        self._tree.setSortingEnabled(False)
        self._tree.setStyleSheet(_GRID_STYLE)

        hdr = self._tree.header()
        hdr.setDefaultAlignment(Qt.AlignCenter)
        hdr.setSectionResizeMode(COL_CHECK, QHeaderView.Fixed)
        hdr.setSectionResizeMode(COL_FLAG,  QHeaderView.Fixed)
        hdr.setSectionResizeMode(COL_NUM,   QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(COL_NAME,  QHeaderView.Stretch)
        for c in _AMOUNT_COLS:
            hdr.setSectionResizeMode(c, QHeaderView.Interactive)
        hdr.setContextMenuPolicy(Qt.CustomContextMenu)
        hdr.customContextMenuRequested.connect(self._on_header_context_menu)

        self._tree.setColumnWidth(COL_CHECK, 28)
        self._tree.setColumnWidth(COL_FLAG,  28)
        for c in _AMOUNT_COLS:
            self._tree.setColumnWidth(c, 112)

        # Center-align all column header labels
        for c in range(len(HEADERS)):
            self._tree.headerItem().setTextAlignment(c, Qt.AlignCenter)

        self._tree.itemClicked.connect(self._on_item_clicked)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self._tree)

        # sticky totals row — sits outside the scroll area, always visible
        self._totals_tree = QTreeWidget()
        self._totals_tree.setColumnCount(len(HEADERS))
        self._totals_tree.setHeaderHidden(True)
        self._totals_tree.setRootIsDecorated(False)
        self._totals_tree.setFixedHeight(60)
        self._totals_tree.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._totals_tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._totals_tree.setFocusPolicy(Qt.NoFocus)
        self._totals_tree.setSelectionMode(QTreeWidget.NoSelection)
        self._totals_tree.setStyleSheet(_TOTALS_STYLE)
        layout.addWidget(self._totals_tree)

        # keep totals columns in sync with main grid
        hdr.sectionResized.connect(self._sync_totals_column)

    # ── Data ─────────────────────────────────────────────────────────────

    def refresh(self):
        self._tree.clear()
        with db_connection(self._path) as conn:
            groups         = get_grouped_balances(conn, self._job_id)
            all_groups_list = get_groups(conn, self._job_id)
            group_map       = get_group_members(conn, self._job_id)

        gby = {g["group_id"]: g for g in all_groups_list}

        unmapped_count = len(groups.get("Unmapped", []))
        if unmapped_count:
            self._unmapped_badge.setText(f"  ⚠  {unmapped_count} unmapped account(s)  ")
            self._unmapped_badge.setVisible(True)
        else:
            self._unmapped_badge.setVisible(False)

        row_alt = False
        for fs_key in _FS_ORDER:
            accounts = groups.get(fs_key)
            if not accounts:
                continue

            # financial statement header (Balance Sheet / P&L / Unmapped)
            bg = UNMAPPED_BG if fs_key == "Unmapped" else SECTION_BG
            fg = SECTION_FG
            fs_label = _FS_LABELS.get(fs_key, fs_key)
            fs_item = self._make_section_row(fs_label, accounts, bg, fg, bold=True, indent=0)
            self._tree.addTopLevelItem(fs_item)
            fs_item.setExpanded(True)

            # group by tax line
            line_groups: dict[str, list[dict]] = {}
            for a in accounts:
                line_groups.setdefault(a["line_name"], []).append(a)

            for line_name, line_accounts in line_groups.items():
                sub_item = self._make_section_row(
                    f"  {line_name}", line_accounts,
                    SUBSECTION_BG, SUBSECTION_FG, bold=False, indent=1,
                )
                fs_item.addChild(sub_item)
                sub_item.setExpanded(True)

                # Split accounts within this tax line into grouped / ungrouped
                grouped_accts: dict[str, list[dict]] = {}
                ungrouped_accts: list[dict] = []
                for acct in line_accounts:
                    gid = group_map.get(acct["account_id"])
                    if gid and gid in gby:
                        grouped_accts.setdefault(gid, []).append(acct)
                    else:
                        ungrouped_accts.append(acct)

                # Render each group as a collapsible header node
                for gid, g_accts in sorted(
                    grouped_accts.items(),
                    key=lambda x: gby[x[0]].get("sort_order", 0),
                ):
                    grp_item = self._make_group_row(gby[gid]["name"], g_accts)
                    sub_item.addChild(grp_item)
                    grp_item.setExpanded(True)
                    for acct in g_accts:
                        row_item = self._make_account_row(acct, row_alt, in_group=True)
                        grp_item.addChild(row_item)
                        row_alt = not row_alt

                # Render ungrouped accounts directly under the tax line
                for acct in ungrouped_accts:
                    row_item = self._make_account_row(acct, row_alt)
                    sub_item.addChild(row_item)
                    row_alt = not row_alt

        self._tree.expandAll()
        self._refresh_totals(groups)
        self._apply_col_visibility()

    def _refresh_totals(self, groups: dict):
        self._totals_tree.clear()
        all_accounts = [a for accts in groups.values() for a in accts]
        totals = _sum_columns(all_accounts) if all_accounts else {k: 0.0 for k in _AMOUNT_KEYS}

        font = QFont()
        font.setBold(True)
        zero_color = QColor("#FFFFFF")
        off_color  = QColor("#FF6B6B")

        # Row 1 — grand total (should net to ≈0 if balanced)
        item = QTreeWidgetItem()
        item.setText(COL_NAME, "TOTAL")
        item.setTextAlignment(COL_NAME, Qt.AlignLeft | Qt.AlignVCenter)
        for col, key in zip(_AMOUNT_COLS, _AMOUNT_KEYS):
            val = totals[key]
            item.setText(col, fmt_amount(val))
            item.setTextAlignment(col, Qt.AlignRight | Qt.AlignVCenter)
            item.setFont(col, font)
            item.setForeground(col, QBrush(off_color if abs(val) > 0.005 else zero_color))
        item.setFont(COL_NAME, font)
        item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
        self._totals_tree.addTopLevelItem(item)

        # Row 2 — Net Income (P&L accounts only, sign-flipped for display)
        pl_accounts = groups.get("ProfitAndLoss", [])
        if pl_accounts:
            pl_totals = _sum_columns(pl_accounts)
            ni_item = QTreeWidgetItem()
            ni_item.setText(COL_NAME, "NET INCOME")
            ni_item.setTextAlignment(COL_NAME, Qt.AlignLeft | Qt.AlignVCenter)
            ni_item.setFont(COL_NAME, font)
            for col, key in zip(_AMOUNT_COLS, _AMOUNT_KEYS):
                ni = round(-pl_totals[key], 2)
                ni_item.setText(col, fmt_amount(ni))
                ni_item.setTextAlignment(col, Qt.AlignRight | Qt.AlignVCenter)
                ni_item.setFont(col, font)
                # positive = profitable (white), negative = loss (pink)
                ni_item.setForeground(col, QBrush(zero_color if ni >= 0 else off_color))
            ni_item.setFlags(ni_item.flags() & ~Qt.ItemIsSelectable)
            self._totals_tree.addTopLevelItem(ni_item)

        # sync column widths from main grid
        main_hdr = self._tree.header()
        for c in range(len(HEADERS)):
            self._totals_tree.setColumnWidth(c, main_hdr.sectionSize(c))

    def _apply_col_visibility(self, *_):
        """Show/hide amount columns in both the main tree and totals tree."""
        for cb, col in self._col_checks:
            hidden = not cb.isChecked()
            self._tree.setColumnHidden(col, hidden)
            self._totals_tree.setColumnHidden(col, hidden)
        # Re-sync totals widths after visibility changes
        main_hdr = self._tree.header()
        for c in range(len(HEADERS)):
            self._totals_tree.setColumnWidth(c, main_hdr.sectionSize(c))

    def _open_mapping_workbench(self):
        from atbworkup.ui.mapping_workbench import MappingWorkbench
        dlg = MappingWorkbench(
            self._path, self._job_id,
            self._entity_type, self._performed_by,
            parent=self,
        )
        dlg.exec()
        self.refresh()

    def _sync_totals_column(self, logical: int, _old: int, new_size: int):
        self._totals_tree.setColumnWidth(logical, new_size)

    # ── Row factories ─────────────────────────────────────────────────────

    def _make_section_row(
        self, label: str, accounts: list[dict],
        bg: QColor, fg: QColor, bold: bool, indent: int,
    ) -> QTreeWidgetItem:
        item = QTreeWidgetItem()
        totals = _sum_columns(accounts)

        label_font = QFont()
        label_font.setBold(bold)
        item.setText(COL_NAME, label)
        item.setFont(COL_NAME, label_font)

        # Base styling for every column: background + the row's given
        # foreground (covers the label/flag/number columns).
        for c in range(len(HEADERS)):
            item.setBackground(c, QBrush(bg))
            item.setForeground(c, QBrush(fg))

        # Amount columns resolve their color purely from sign + whether this
        # is a dark-background row (bold=True is only ever passed for the
        # FS-level banner rows, which have a navy/dark-red fill) — decided in
        # ONE pass. A previous "set, then blanket-overwrite, then re-fix
        # negatives only" version of this left positive totals on a
        # tax-line's own grouping row sharing the same navy tone as the
        # background tint, making them hard to read.
        amt_font = QFont()
        amt_font.setBold(True)
        dark_bg = bold
        pos_color = QColor("#FFFFFF") if dark_bg else TEXT_PRIMARY
        neg_color = QColor("#FFAAAA") if dark_bg else TEXT_CREDIT
        for col, key in zip(_AMOUNT_COLS, _AMOUNT_KEYS):
            val = totals[key]
            item.setText(col, fmt_amount(val))
            item.setTextAlignment(col, Qt.AlignRight | Qt.AlignVCenter)
            item.setFont(col, amt_font)
            item.setForeground(col, QBrush(neg_color if val < 0 else pos_color))

        item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
        return item

    def _make_group_row(self, name: str, accounts: list[dict]) -> QTreeWidgetItem:
        """Collapsible group header within a tax-line subsection."""
        item = QTreeWidgetItem()
        totals = _sum_columns(accounts)
        n = len(accounts)
        font = QFont()
        font.setBold(True)
        font.setPointSize(font.pointSize())  # explicit size so it's not inherited as italic
        # Prefix with ▸ so it reads as a collapsible group, not an account row
        name_lbl = f"▸ {name}  ({n} accounts)"
        item.setText(COL_NAME, name_lbl)
        item.setFont(COL_NAME, font)
        # Darker, more distinct background than plain account rows
        bg = QColor("#C8D4EE")   # medium navy-tint — clearly different from account rows
        fg = QColor("#1A2B4C")   # full navy
        for c in range(len(HEADERS)):
            item.setBackground(c, QBrush(bg))
            item.setForeground(c, QBrush(fg))
        for col, key in zip(_AMOUNT_COLS, _AMOUNT_KEYS):
            val = totals[key]
            item.setText(col, fmt_amount(val))
            item.setTextAlignment(col, Qt.AlignRight | Qt.AlignVCenter)
            item.setFont(col, font)
            if val < 0:
                item.setForeground(col, QBrush(TEXT_CREDIT))
        item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
        return item

    def _apply_flag_display(self, item: QTreeWidgetItem, account_id: str):
        """Set COL_FLAG text/color from the preparer flag only (unaffected by reviewer notes)."""
        flag = item.data(COL_FLAG, Qt.UserRole)
        symbol, flag_color = _FLAG_DISPLAY.get(flag, ("", QColor("transparent")))
        item.setText(COL_FLAG, symbol)
        item.setForeground(COL_FLAG, QBrush(flag_color))
        item.setTextAlignment(COL_FLAG, Qt.AlignCenter | Qt.AlignVCenter)

    def _make_account_row(self, acct: dict, alt: bool, in_group: bool = False) -> QTreeWidgetItem:
        item = QTreeWidgetItem()
        item.setData(COL_CHECK, Qt.UserRole, acct["account_id"])
        item.setCheckState(COL_CHECK, Qt.Unchecked)

        # store the preparer flag value for cycling; display may be overridden by reviewer R
        flag = acct.get("flag")
        item.setData(COL_FLAG, Qt.UserRole, flag)
        self._apply_flag_display(item, acct["account_id"])

        item.setText(COL_NUM,  acct.get("account_number") or "")
        item.setText(COL_NAME, "     " + acct["account_name"] if in_group else acct["account_name"])

        if in_group:
            # Faint navy tint ties these rows visually to their group header
            bg = QColor("#EEF1F9") if alt else QColor("#E6EAF6")
        else:
            bg = ROW_BG_EVEN if alt else ROW_BG_ODD
        for c in range(len(HEADERS)):
            item.setBackground(c, QBrush(bg))
            item.setForeground(c, QBrush(TEXT_PRIMARY))

        for col, key in zip(_AMOUNT_COLS, _AMOUNT_KEYS):
            val = acct[key]
            item.setText(col, fmt_amount(val))
            item.setTextAlignment(col, Qt.AlignRight | Qt.AlignVCenter)
            if val < 0:
                item.setForeground(col, QBrush(TEXT_CREDIT))
            elif val == 0:
                item.setForeground(col, QBrush(TEXT_MUTED))

        # Reviewer note indicator — amber ⚠ prefix on the name column only
        if acct["account_id"] in self._reviewer_note_ids:
            indent = "     " if in_group else ""
            item.setText(COL_NAME, indent + "⚠  " + acct["account_name"])
            item.setForeground(COL_NAME, QBrush(QColor("#B8860B")))

        return item

    # ── Interaction ───────────────────────────────────────────────────────

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        account_id = item.data(COL_CHECK, Qt.UserRole)
        if not account_id:
            return
        _JE_COL_MAP = {COL_AJE: "AJE", COL_RJE: "RJE", COL_FTJE: "FTJE"}
        entry_type = _JE_COL_MAP.get(column)
        if entry_type:
            self.je_requested.emit(account_id, entry_type)

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        account_id = item.data(COL_CHECK, Qt.UserRole)
        if account_id is None:
            # Section or group header row — clicking anywhere on the row toggles expand
            if item.childCount() > 0:
                item.setExpanded(not item.isExpanded())
            return
        if column == COL_FLAG:
            self._cycle_flag(item, account_id)

    def _cycle_flag(self, item: QTreeWidgetItem, account_id: str):
        current = item.data(COL_FLAG, Qt.UserRole)
        try:
            idx = _FLAG_CYCLE.index(current)
        except ValueError:
            idx = 0
        next_flag = _FLAG_CYCLE[(idx + 1) % len(_FLAG_CYCLE)]
        item.setData(COL_FLAG, Qt.UserRole, next_flag)
        self._apply_flag_display(item, account_id)

        with db_connection(self._path) as conn:
            set_flag(conn, account_id, next_flag)

    def _on_context_menu(self, pos):
        item = self._tree.itemAt(pos)
        if not item:
            return
        # only show menu on account rows (have account_id data)
        if not item.data(COL_CHECK, Qt.UserRole):
            return

        # Use Qt selection model — Ctrl+Click, Shift+Click, Ctrl+A all work.
        # If the right-clicked row isn't in the selection, treat it as a
        # single-row selection (matches standard list/tree UX convention).
        selected_ids = self._selected_account_ids_from_selection()
        clicked_id = item.data(COL_CHECK, Qt.UserRole)
        if clicked_id not in selected_ids:
            target_ids = [clicked_id]
        else:
            target_ids = selected_ids

        menu = QMenu(self)
        count = len(target_ids)
        map_action = menu.addAction(
            f"Map {count} account{'s' if count != 1 else ''} to Tax Line…"
        )
        group_action = menu.addAction(
            f"Add {count} account{'s' if count != 1 else ''} to Group…"
        )
        menu.addSeparator()
        note_action     = menu.addAction("Add Note…")
        new_acct_action = menu.addAction("New Account…")
        menu.addSeparator()
        edit_num_action  = None
        edit_name_action = None
        if len(target_ids) == 1:
            edit_num_action  = menu.addAction("Edit Account Number…")
            edit_name_action = menu.addAction("Edit Account Name…")
            menu.addSeparator()
        del_action = menu.addAction(
            f"Delete {count} Account{'s' if count != 1 else ''}…"
        )

        action = menu.exec(self._tree.viewport().mapToGlobal(pos))
        if action == map_action:
            self._open_mapping_dialog(target_ids)
        elif action == group_action:
            self._open_group_dialog(target_ids)
        elif action == note_action:
            name = item.text(COL_NAME)
            self.note_requested.emit(clicked_id, name)
        elif action == new_acct_action:
            self._on_new_account()
        elif action == edit_num_action:
            self._edit_account_field(clicked_id, item, "number")
        elif action == edit_name_action:
            self._edit_account_field(clicked_id, item, "name")
        elif action == del_action:
            self._delete_accounts(target_ids)

    def _selected_account_ids_from_selection(self) -> list[str]:
        """Account IDs from the Qt selection highlight (not checkboxes)."""
        return [
            item.data(COL_CHECK, Qt.UserRole)
            for item in self._tree.selectedItems()
            if item.data(COL_CHECK, Qt.UserRole)
        ]

    def _open_mapping_dialog(self, account_ids: list[str]):
        from atbworkup.ui.mapping_dialog import MappingDialog
        # fetch display names for the summary label
        with db_connection(self._path) as conn:
            names = []
            for aid in account_ids:
                row = conn.execute(
                    "SELECT account_name FROM accounts WHERE account_id = ?", (aid,)
                ).fetchone()
                if row:
                    names.append(row["account_name"])

        dlg = MappingDialog(
            self._path, self._job_id, self._entity_type,
            account_ids, names, self._performed_by, parent=self,
        )
        if dlg.exec() == MappingDialog.Accepted:
            self.refresh()

    def _open_group_dialog(self, account_ids: list[str]):
        from atbworkup.ui.group_dialog import GroupPickerDialog
        from atbworkup.models.groups import add_accounts_to_group
        with db_connection(self._path) as conn:
            names = []
            for aid in account_ids:
                row = conn.execute(
                    "SELECT account_name FROM accounts WHERE account_id = ?", (aid,)
                ).fetchone()
                if row:
                    names.append(row["account_name"])
        dlg = GroupPickerDialog(self._path, self._job_id, account_ids, names, parent=self)
        if dlg.exec() == GroupPickerDialog.Accepted:
            group_id = dlg.chosen_group_id()
            if group_id:
                with db_connection(self._path) as conn:
                    add_accounts_to_group(conn, group_id, account_ids)
                self.refresh()

    def _delete_accounts(self, account_ids: list[str]):
        from PySide6.QtWidgets import QMessageBox
        # Fetch names for the confirmation message
        with db_connection(self._path) as conn:
            names = []
            for aid in account_ids:
                row = conn.execute(
                    "SELECT account_name FROM accounts WHERE account_id = ?", (aid,)
                ).fetchone()
                if row:
                    names.append(row["account_name"])

        noun = f"{len(names)} account{'s' if len(names) != 1 else ''}"
        preview = "\n".join(f"  • {n}" for n in names[:10])
        if len(names) > 10:
            preview += f"\n  … and {len(names) - 10} more"

        reply = QMessageBox.warning(
            self, f"Delete {noun}",
            f"Permanently delete {noun}?\n\n{preview}\n\n"
            "Accounts with existing journal entry lines cannot be deleted.",
            QMessageBox.Ok | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if reply != QMessageBox.Ok:
            return

        with db_connection(self._path) as conn:
            deleted, blocked = delete_accounts(conn, account_ids)

        if blocked:
            QMessageBox.warning(
                self, "Some Accounts Skipped",
                f"Deleted {len(deleted)}, skipped {len(blocked)} "
                f"(have journal entry lines):\n"
                + "\n".join(f"  • {n}" for n in blocked),
            )
        self.refresh()

    def _edit_account_field(self, account_id: str, item: QTreeWidgetItem, field: str):
        """Inline-edit account_number or account_name via an input dialog."""
        from PySide6.QtWidgets import QInputDialog
        from atbworkup.models.accounts import update_account

        with db_connection(self._path) as conn:
            row = conn.execute(
                "SELECT account_number, account_name FROM accounts WHERE account_id = ?",
                (account_id,),
            ).fetchone()
        if not row:
            return

        if field == "number":
            current = row["account_number"] or ""
            label   = "Account Number:"
        else:
            current = row["account_name"]
            label   = "Account Name:"

        new_val, ok = QInputDialog.getText(
            self, "Edit Account", label, text=current
        )
        if not ok:
            return
        new_val = new_val.strip()
        if new_val == current:
            return

        # Duplicate number check
        if field == "number" and new_val:
            with db_connection(self._path) as conn:
                dup = conn.execute(
                    "SELECT account_id FROM accounts "
                    "WHERE job_id = ? AND account_number = ? AND account_id != ?",
                    (self._job_id, new_val, account_id),
                ).fetchone()
            if dup:
                QMessageBox.warning(
                    self, "Duplicate Account Number",
                    f"Account number '{new_val}' is already used by another account."
                )
                return

        with db_connection(self._path) as conn:
            if field == "number":
                update_account(conn, account_id, account_number=new_val or None)
            else:
                if not new_val:
                    QMessageBox.warning(self, "Required", "Account name cannot be blank.")
                    return
                update_account(conn, account_id, account_name=new_val)
        self.refresh()

    def _on_header_context_menu(self, pos):
        """Right-click on column header → reset column widths."""
        from PySide6.QtWidgets import QMenu as _QMenu
        menu = _QMenu(self)
        reset_action = menu.addAction("Reset Column Widths")
        action = menu.exec(self._tree.header().mapToGlobal(pos))
        if action == reset_action:
            for c in _AMOUNT_COLS:
                self._tree.setColumnWidth(c, 112)

    def _on_new_account(self):
        from atbworkup.ui.new_account_dialog import NewAccountDialog
        dlg = NewAccountDialog(
            self._path, self._job_id,
            self._entity_type, self._performed_by,
            parent=self,
        )
        if dlg.exec() == NewAccountDialog.Accepted:
            self.refresh()
            self.account_created.emit()

    def set_reviewer_note_ids(self, ids: set):
        """Update the amber ⚠ indicator on account name column for reviewer notes."""
        self._reviewer_note_ids = ids
        it = QTreeWidgetItemIterator(self._tree)
        while it.value():
            item = it.value()
            account_id = item.data(COL_CHECK, Qt.UserRole)
            if account_id:
                # Strip or add the ⚠ prefix on COL_NAME without touching COL_FLAG
                name = item.text(COL_NAME)
                if name.startswith("⚠  "):
                    name = name[3:]
                if account_id in ids:
                    item.setText(COL_NAME, "⚠  " + name)
                    item.setForeground(COL_NAME, QBrush(QColor("#B8860B")))
                else:
                    item.setText(COL_NAME, name)
                    item.setForeground(COL_NAME, QBrush(TEXT_PRIMARY))
            it += 1

    def navigate_to_account(self, account_id: str):
        """Scroll to and highlight the row for the given account_id."""
        it = QTreeWidgetItemIterator(self._tree)
        while it.value():
            item = it.value()
            if item.data(COL_CHECK, Qt.UserRole) == account_id:
                self._tree.scrollToItem(item)
                self._tree.setCurrentItem(item)
                return
            it += 1

    def selected_account_ids(self) -> list[str]:
        ids = []
        it = QTreeWidgetItemIterator(self._tree, QTreeWidgetItemIterator.Checked)
        while it.value():
            aid = it.value().data(COL_CHECK, Qt.UserRole)
            if aid:
                ids.append(aid)
            it += 1
        return ids


# ── Helpers ───────────────────────────────────────────────────────────────

def _sum_columns(accounts: list[dict]) -> dict:
    return {key: round(sum(a[key] for a in accounts), 2) for key in _AMOUNT_KEYS}
