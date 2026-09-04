"""
Consolidation window — aggregates subsidiary binders into a combined
financial statement view with eliminating journal entries.

Only exists for binders with entity_type = 'Consolidated'.

Column progression from subsidiaries:
  UNADJ  = pbc_balance
  +AJE   = adj_balance
  +RJE   = final_balance   ← what we aggregate here (book-final)
  +FTJE  = ftax_balance    ← also carried for Tax Entries column in summary
"""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QFileDialog, QMessageBox, QTabWidget, QStatusBar, QToolBar,
    QTreeWidget, QTreeWidgetItem, QFrame,
    QComboBox, QLineEdit, QCompleter, QAbstractItemView, QMenu,
    QDialog, QDialogButtonBox, QListWidget, QListWidgetItem,
)
from PySide6.QtCore import Qt, QSize, Signal, QStringListModel
from PySide6.QtGui import QFont, QColor, QBrush

from atbworkup.db.connection import db_connection
from atbworkup.utils.ids import new_uuid
from atbworkup.models import consolidation_entries as ce_model
from atbworkup.models import consolidation_groups as cg_model
from atbworkup.models import consolidation_read
from atbworkup.models import consolidation_calc
from atbworkup.data.tax_line_categories import (
    classify_section as _classify_section,
    CATEGORY_REVENUE, CATEGORY_COGS, CATEGORY_SCHEDULE_K,
)

import datetime

_NAVY       = "#1A2B4C"
_SECTION_BG = "#F2F4F6"
_AMBER      = "#B85C00"
_GREEN      = "#2A6A4A"
_PURPLE     = "#6B2D8B"
_ELIM_FG    = "#B85C00"

_HDR_STYLE = (
    f"QHeaderView::section {{ background: {_NAVY}; color: white; "
    "font-size: 12px; font-weight: bold; padding: 4px 8px; border: none; "
    "border-right: 1px solid #2A3B5C; }}"
)
_BTN = (
    f"QPushButton {{ font-size: 11px; font-weight: bold; padding: 5px 14px; "
    f"border: 2px solid {_NAVY}; border-radius: 3px; "
    f"background: #FFFFFF; color: {_NAVY}; }} "
    f"QPushButton:hover {{ background: #E4EEFB; }} "
    f"QPushButton:checked {{ background: {_NAVY}; color: #FFFFFF; }}"
)
_BTN_NAVY = (
    f"QPushButton {{ font-size: 11px; padding: 5px 14px; border-radius: 3px; "
    f"background: {_NAVY}; color: #FFF; font-weight: bold; border: 2px solid {_NAVY}; }} "
    f"QPushButton:hover {{ background: #2A3B6C; }}"
)
_BTN_GREEN = (
    "QPushButton { font-size: 11px; padding: 5px 14px; border-radius: 3px; "
    "background: #4A7A4A; color: #FFF; font-weight: bold; border: 2px solid #3A6A3A; } "
    "QPushButton:hover { background: #3A6A3A; }"
)


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fmt(v: float) -> str:
    if abs(v) < 0.005:
        return "—"
    return f"({abs(v):,.2f})" if v < 0 else f"{v:,.2f}"


def _mono_bold() -> QFont:
    return QFont("Consolas", -1, QFont.Bold)


def _mono() -> QFont:
    return QFont("Consolas")


def _bold() -> QFont:
    return QFont("Segoe UI", -1, QFont.Bold)


# ── Member data structures ────────────────────────────────────────────────────
# {section_name: {line_name: {"final": float, "ftax": float, "sort": int}}}
SectionData = dict[str, dict[str, dict]]
# {section_name: {line_name: [{"name": str, "number": str, "final": float}]}}
AccountDetail = dict[str, dict[str, list[dict]]]


class ConsolidationWindow(QMainWindow):
    """
    Manages a consolidated binder: links subsidiary .atbr.xlsx files,
    shows combined financial statements, and allows eliminating entries.
    """

    def __init__(self, path: Path, job: dict,
                 source_xlsx: Path | None = None,
                 performed_by: str = "",
                 parent=None):
        super().__init__(parent)
        self._path         = Path(path)
        self._source_xlsx  = Path(source_xlsx) if source_xlsx else None
        self._job          = job
        self._performed_by = performed_by
        # Stores per-member financials for summary tab
        self._member_bs:   list[tuple[str, SectionData]] = []   # [(name, bs_data)]
        self._member_pl:   list[tuple[str, SectionData]] = []   # [(name, pl_data)]
        # Cached combined data for detail toggle without re-reading disk
        self._combined_bs:     SectionData = {}
        self._combined_pl:     SectionData = {}
        self._elim_by_section: dict[str, float] = {}
        self._cte_by_section:  dict[str, float] = {}
        self._combined_net_income: float = 0.0
        self._sch_k_grand_override: float | None = None
        self._consol_groups: list[dict] = []
        self._consol_group_members: dict[tuple[str, str], str] = {}
        self._detail_bs:       list[tuple[str, AccountDetail]] = []
        self._detail_pl:       list[tuple[str, AccountDetail]] = []
        self._build_ui()
        self._refresh_members()
        self._refresh_combined()

    def _build_ui(self):
        self.setWindowTitle(
            f"Consolidated — {self._job['client_name']} {self._job['tax_year']}"
        )
        self.setMinimumSize(1200, 720)

        # ── Toolbar ──────────────────────────────────────────────────────
        tb = QToolBar("Main")
        tb.setMovable(False)
        tb.setStyleSheet(
            "QToolBar { background: #E5E5E5; border-bottom: 1px solid #CCCCCC; "
            "padding: 2px 6px; spacing: 6px; }"
        )
        self.addToolBar(tb)

        self._save_btn = QPushButton("Save")
        self._save_btn.setStyleSheet(_BTN_GREEN)
        self._save_btn.clicked.connect(self._on_save)
        tb.addWidget(self._save_btn)

        btn_recalc = QPushButton("Recalculate")
        btn_recalc.setStyleSheet(_BTN_NAVY)
        btn_recalc.clicked.connect(self._refresh_combined)
        tb.addWidget(btn_recalc)

        self._btn_detail = QPushButton("Show Account Detail")
        self._btn_detail.setCheckable(True)
        self._btn_detail.setStyleSheet(_BTN)
        self._btn_detail.toggled.connect(self._apply_detail_toggle)
        tb.addWidget(self._btn_detail)

        self._btn_expand = QPushButton("⊞  Expand All")
        self._btn_expand.setStyleSheet(_BTN)
        self._btn_expand.setToolTip("Expand / collapse all nodes in the current tree")
        self._btn_expand.clicked.connect(self._on_toggle_expand)
        self._btn_expand._expanded = False
        tb.addWidget(self._btn_expand)

        self._btn_export = QPushButton("Export PDF…")
        self._btn_export.setStyleSheet(_BTN_NAVY)
        self._btn_export.clicked.connect(self._on_export_pdf)
        tb.addWidget(self._btn_export)

        # ── Tabs (Subsidiaries tab first, then combined financials) ───────
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)

        # ── Subsidiaries tab: member list ─────────────────────────────────
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(8, 8, 8, 8)

        hdr_label = QLabel("Subsidiary Binders")
        hdr_label.setFont(QFont("Segoe UI", 11, QFont.Bold))

        btn_row = QHBoxLayout()
        btn_add = QPushButton("+ Add Subsidiary…")
        btn_add.setStyleSheet(_BTN_NAVY)
        btn_add.clicked.connect(self._on_add_member)
        btn_rem = QPushButton("Remove")
        btn_rem.setStyleSheet(_BTN)
        btn_rem.clicked.connect(self._on_remove_member)
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_rem)
        btn_row.addStretch()

        self._member_table = QTableWidget(0, 5)
        self._member_table.setHorizontalHeaderLabels(["Name", "Code", "Entity", "Year", "Status"])
        self._member_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._member_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self._member_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._member_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._member_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self._member_table.setColumnWidth(1, 54)
        self._member_table.horizontalHeader().setStyleSheet(_HDR_STYLE)
        self._member_table.verticalHeader().setVisible(False)
        self._member_table.setAlternatingRowColors(True)
        self._member_table.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed)
        self._member_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._member_table.itemChanged.connect(self._on_member_code_changed)

        left_layout.addWidget(hdr_label)
        left_layout.addLayout(btn_row)
        left_layout.addWidget(self._member_table)

        # ── Remaining tabs: combined financials, entries, notes ───────────
        self._bs_tree        = self._make_combined_tree()
        self._pl_tree        = self._make_combined_tree()
        self._summary_widget = _SummaryWidget()

        from atbworkup.ui.notes_panel import NotesDock
        _notes_dock = NotesDock(
            self._path, self._job["job_id"],
            performed_by=self._performed_by, role="preparer",
        )
        # Extract the inner widget so it can be embedded in a tab (QDockWidget can't be tabbed)
        self._notes_panel_tab = _notes_dock.widget()
        self._notes_panel_tab.setParent(None)
        self._notes_dock_ref = _notes_dock   # keep alive for refresh() calls

        self._entry_panel = _EntryTabPanel(self._path, self._job["job_id"])
        self._entry_panel.changed.connect(self._refresh_combined)

        self._tabs.addTab(left,                 "Subsidiaries")
        self._tabs.addTab(self._bs_tree,        "Combined Balance Sheet")
        self._tabs.addTab(self._pl_tree,        "Combined P&L")
        self._tabs.addTab(self._summary_widget, "Consolidation Summary")
        self._tabs.addTab(self._notes_panel_tab, "Notes")
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self._tabs.setCurrentIndex(1)   # open on Combined Balance Sheet, not the setup tab

        # ── Entry panel docked below, like the regular binder's JE panel ──
        entry_wrap = QWidget()
        ewl = QVBoxLayout(entry_wrap)
        ewl.setContentsMargins(0, 0, 0, 0)
        ewl.setSpacing(0)

        entry_hdr = QWidget()
        entry_hdr.setFixedHeight(28)
        entry_hdr.setStyleSheet(f"background: {_NAVY};")
        ehl = QHBoxLayout(entry_hdr)
        ehl.setContentsMargins(10, 0, 6, 0)
        entry_title = QLabel("Eliminating & Tax Entries")
        entry_title.setStyleSheet(
            "color: #FFFFFF; font-weight: bold; font-size: 11px; letter-spacing: 1px;"
        )
        ehl.addWidget(entry_title)
        ehl.addStretch()
        self._entry_hide_btn = QPushButton("▼  Hide")
        self._entry_hide_btn.setToolTip("Collapse / show the entry editor")
        self._entry_hide_btn.setFixedHeight(20)
        self._entry_hide_btn.setStyleSheet(
            "background: rgba(255,255,255,0.15); color: #FFFFFF; font-size: 10px; "
            "font-weight: bold; padding: 0 8px; border-radius: 3px; border: none;"
        )
        self._entry_hide_btn.clicked.connect(self._on_toggle_entry_panel)
        ehl.addWidget(self._entry_hide_btn)

        ewl.addWidget(entry_hdr)
        ewl.addWidget(self._entry_panel, 1)

        self._main_splitter = QSplitter(Qt.Vertical)
        self._main_splitter.setChildrenCollapsible(True)
        self._main_splitter.addWidget(self._tabs)
        self._main_splitter.addWidget(entry_wrap)
        self._main_splitter.setSizes([480, 260])
        self.setCentralWidget(self._main_splitter)

        # Status bar
        sb = QStatusBar()
        self._status_msg = QLabel()
        sb.addWidget(self._status_msg)
        self.setStatusBar(sb)

    def _make_combined_tree(self) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setColumnCount(6)
        tree.setHeaderLabels([
            "Account / Section",
            "Combined FINAL", "EJEs", "Net Consolidated",
            "Tax Entries (CTE)", "Net Tax",
        ])
        hdr = tree.header()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, 6):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hdr.setDefaultAlignment(Qt.AlignRight | Qt.AlignVCenter)
        hdr.setStyleSheet(
            f"QHeaderView::section {{ background: {_NAVY}; color: white; "
            "font-size: 12px; font-weight: bold; padding: 5px 10px; "
            "border: none; border-right: 1px solid #2A3B5C; }}"
        )
        tree.setAlternatingRowColors(False)
        tree.setRootIsDecorated(True)
        tree.setStyleSheet(
            "QTreeWidget { background: #FFF; border: none; font-size: 13px; }"
            "QTreeWidget::item { padding: 3px 6px; }"
        )
        tree.setContextMenuPolicy(Qt.CustomContextMenu)
        tree.customContextMenuRequested.connect(
            lambda pos, t=tree: self._on_tree_context_menu(t, pos)
        )
        return tree

    def _on_tree_context_menu(self, tree: QTreeWidget, pos):
        item = tree.itemAt(pos)
        if item is None:
            return
        info = item.data(0, Qt.UserRole)
        if not info:
            return

        menu = QMenu(self)
        if info["kind"] == "account":
            targets = [(info["member_id"], info["account_id"], info["label"])]
        else:   # "line" — every account under this tax line, across all subs
            targets = info["accounts"]
            if not targets:
                return

        if len(targets) == 1:
            mid, aid, label = targets[0]
            a1 = menu.addAction(f"Create Eliminating Entry (EJE) — {label}")
            a1.triggered.connect(
                lambda _=False, m=mid, a=aid: self._open_entry_for_account("elim", m, a)
            )
            a2 = menu.addAction(f"Create Tax Entry (CTE) — {label}")
            a2.triggered.connect(
                lambda _=False, m=mid, a=aid: self._open_entry_for_account("cte", m, a)
            )
            menu.addSeparator()
            a3 = menu.addAction(f"Add to Group… — {label}")
            a3.triggered.connect(
                lambda _=False, m=mid, a=aid: self._on_add_to_group(m, a)
            )
        else:
            eje_menu = menu.addMenu("Create Eliminating Entry (EJE) for…")
            cte_menu = menu.addMenu("Create Tax Entry (CTE) for…")
            for mid, aid, label in targets:
                a1 = eje_menu.addAction(label)
                a1.triggered.connect(
                    lambda _=False, m=mid, a=aid: self._open_entry_for_account("elim", m, a)
                )
                a2 = cte_menu.addAction(label)
                a2.triggered.connect(
                    lambda _=False, m=mid, a=aid: self._open_entry_for_account("cte", m, a)
                )
            menu.addSeparator()
            group_menu = menu.addMenu("Add to Group…")
            for mid, aid, label in targets:
                a3 = group_menu.addAction(label)
                a3.triggered.connect(
                    lambda _=False, m=mid, a=aid: self._on_add_to_group(m, a)
                )
        menu.exec(tree.viewport().mapToGlobal(pos))

    def _open_entry_for_account(self, workpaper: str, member_id: str, account_id: str):
        sizes = self._main_splitter.sizes()
        if sizes and sizes[-1] <= 32:
            self._on_toggle_entry_panel()   # expand if currently collapsed
        self._entry_panel.open_new_entry_for_account(workpaper, member_id, account_id)

    def _on_add_to_group(self, member_id: str, account_id: str):
        dlg = _ConsolGroupPickerDialog(self._consol_groups, self)
        if dlg.exec() != QDialog.Accepted:
            return
        with db_connection(self._path) as conn:
            if dlg.new_group_name():
                group_id = cg_model.create_group(
                    conn, job_id=self._job["job_id"], name=dlg.new_group_name(),
                    sort_order=len(self._consol_groups),
                )
            else:
                group_id = dlg.selected_group_id()
            if group_id:
                cg_model.add_member(conn, group_id, member_id, account_id)
        self._refresh_combined()

    # ── Members ───────────────────────────────────────────────────────────

    def _refresh_members(self):
        self._member_table.blockSignals(True)
        self._member_table.setRowCount(0)
        with db_connection(self._path) as conn:
            rows = conn.execute(
                "SELECT member_id, member_name, member_code, file_path, member_type "
                "FROM consolidation_members WHERE job_id = ? ORDER BY sort_order",
                (self._job["job_id"],),
            ).fetchall()
        for row in rows:
            r = self._member_table.rowCount()
            self._member_table.insertRow(r)
            year_text   = "—"
            entity_text = "—"
            status_text = "—"
            fp = Path(row["file_path"])
            if fp.exists():
                try:
                    info = _read_member_info(fp)
                    year_text   = str(info.get("tax_year", "—"))
                    entity_text = info.get("entity_type", "—")
                    status_text = info.get("status", "—")
                except Exception:
                    status_text = "⚠ Error"
            else:
                status_text = "⚠ Not Found"

            name_item = QTableWidgetItem(row["member_name"])
            name_item.setData(Qt.UserRole, row["member_id"])
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)

            code_item = QTableWidgetItem(row["member_code"] or "")
            code_item.setData(Qt.UserRole, row["member_id"])
            code_item.setToolTip("Double-click to set 2-5 letter code (e.g. ABD, PAR)")

            entity_item = QTableWidgetItem(entity_text)
            entity_item.setFlags(entity_item.flags() & ~Qt.ItemIsEditable)
            year_item   = QTableWidgetItem(year_text)
            year_item.setFlags(year_item.flags() & ~Qt.ItemIsEditable)
            status_item = QTableWidgetItem(status_text)
            status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)

            self._member_table.setItem(r, 0, name_item)
            self._member_table.setItem(r, 1, code_item)
            self._member_table.setItem(r, 2, entity_item)
            self._member_table.setItem(r, 3, year_item)
            self._member_table.setItem(r, 4, status_item)
        self._member_table.blockSignals(False)

    def _on_member_code_changed(self, item: "QTableWidgetItem"):
        if item.column() != 1:
            return
        member_id = item.data(Qt.UserRole)
        if not member_id:
            return
        code = item.text().strip().upper()[:5]
        # Enforce uppercase and max 5 chars in the cell
        self._member_table.blockSignals(True)
        item.setText(code)
        self._member_table.blockSignals(False)
        with db_connection(self._path) as conn:
            conn.execute(
                "UPDATE consolidation_members SET member_code = ? WHERE member_id = ?",
                (code, member_id),
            )
        self._refresh_combined()

    def _on_add_member(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Subsidiary Binder", "",
            "TB Workup Files (*.atbr.xlsx);;All Files (*)",
        )
        if not path:
            return
        fp = Path(path)
        try:
            info = _read_member_info(fp)
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Cannot read binder:\n{exc}")
            return
        name = info.get("client_name") or fp.stem
        with db_connection(self._path) as conn:
            sort_order = self._member_table.rowCount()
            conn.execute(
                "INSERT INTO consolidation_members "
                "(member_id, job_id, member_name, file_path, member_type, sort_order, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (new_uuid(), self._job["job_id"], name, str(fp),
                 "subsidiary", sort_order, _now()),
            )
        self._refresh_members()
        self._refresh_combined()

    def _on_remove_member(self):
        rows = {i.row() for i in self._member_table.selectedItems()}
        if not rows:
            return
        ids = [self._member_table.item(r, 0).data(Qt.UserRole)
               for r in rows if self._member_table.item(r, 0)]
        reply = QMessageBox.question(
            self, "Remove Subsidiaries",
            f"Remove {len(ids)} subsidiary binder(s) from this consolidation?\n"
            "(The original files are not deleted.)",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        with db_connection(self._path) as conn:
            for mid in ids:
                conn.execute(
                    "DELETE FROM consolidation_members WHERE member_id = ?", (mid,)
                )
        self._refresh_members()
        self._refresh_combined()

    # ── Combined refresh ──────────────────────────────────────────────────

    def _refresh_combined(self):
        with db_connection(self._path) as conn:
            calc = consolidation_calc.compute_combined(conn, self._job)
            self._consol_groups = cg_model.get_groups(conn, self._job["job_id"])
            self._consol_group_members = cg_model.get_group_members(conn, self._job["job_id"])

        combined_bs = calc["combined_bs"]
        combined_pl = calc["combined_pl"]
        self._member_bs = calc["member_bs"]
        self._member_pl = calc["member_pl"]
        self._detail_bs = calc["detail_bs"]
        self._detail_pl = calc["detail_pl"]
        errors = calc["errors"]
        label_to_member_id = calc["label_to_member_id"]
        self._label_to_member_id = label_to_member_id

        self._entry_panel.set_members(calc["member_dicts"])

        elim_by_account = calc["elim_by_account"]
        cte_by_account  = calc["cte_by_account"]
        self._elim_by_account = elim_by_account
        self._cte_by_account  = cte_by_account

        elim_by_section = calc["elim_by_section"]
        cte_by_section  = calc["cte_by_section"]
        self._combined_bs     = combined_bs
        self._combined_pl     = combined_pl
        self._elim_by_section = elim_by_section
        self._cte_by_section  = cte_by_section

        pl_base_ni = calc["pl_base_ni"]
        pl_elim_ni = calc["pl_elim_ni"]
        pl_cte_ni  = calc["pl_cte_ni"]
        combined_net_income = calc["combined_net_income"]
        self._combined_net_income = combined_net_income

        sch_k_total_ni = calc["sch_k_total_ni"]
        has_sch_k      = calc["has_sch_k"]
        net_elim_total = calc["net_elim_total"]
        net_cte_total  = calc["net_cte_total"]

        show = self._btn_detail.isChecked()
        self._populate_combined_tree(
            self._bs_tree, combined_bs, "Balance Sheet",
            elim_by_section, cte_by_section,
            member_data=self._member_bs,
            detail_list=self._detail_bs, show_detail=show,
            net_income=combined_net_income,
            elim_by_account=elim_by_account, cte_by_account=cte_by_account,
            label_to_member_id=label_to_member_id,
        )
        self._populate_combined_tree(
            self._pl_tree, combined_pl, "P&L",
            elim_by_section, cte_by_section,
            member_data=self._member_pl,
            detail_list=self._detail_pl, show_detail=show,
            pl_grand_override=(pl_base_ni, pl_elim_ni, pl_cte_ni),
            sch_k_grand_override=sch_k_total_ni if has_sch_k else None,
            elim_by_account=elim_by_account, cte_by_account=cte_by_account,
            label_to_member_id=label_to_member_id,
        )
        self._pl_grand_override = (pl_base_ni, pl_elim_ni, pl_cte_ni)
        self._sch_k_grand_override = sch_k_total_ni if has_sch_k else None

        # Refresh summary with current member data
        self._summary_widget.rebuild(
            member_names = calc["member_labels"],
            member_bs    = self._member_bs,
            member_pl    = self._member_pl,
            combined_bs  = combined_bs,
            combined_pl  = combined_pl,
            elim_total   = net_elim_total,
            cte_total    = net_cte_total,
            pl_net_income_base = pl_base_ni,
            pl_elim_ni          = pl_elim_ni,
            pl_cte_ni           = pl_cte_ni,
        )

        # Restore expand/detail state after tree rebuild
        expanded = self._btn_expand._expanded
        self._apply_expand_state(self._bs_tree, expanded)
        self._apply_expand_state(self._pl_tree, expanded)
        # Keep EJE panel table in sync (Recalculate re-reads from disk)
        self._entry_panel.refresh()

        if errors:
            self._status_msg.setText("⚠  " + "  |  ".join(errors))
            self._status_msg.setStyleSheet("color: #CC4400;")
        else:
            count = len(calc["member_labels"])
            self._status_msg.setText(
                f"Combined from {count} subsidiary binder{'s' if count != 1 else ''}."
            )
            self._status_msg.setStyleSheet("color: #2A6A4A;")

    _NCOLS = 6   # Account/Section | FINAL | EJEs | Net Consol. | CTEs | Net Tax

    def _populate_combined_tree(self, tree: QTreeWidget, data: SectionData,
                                 label: str,
                                 elim_by_section: dict[str, float],
                                 cte_by_section:  dict[str, float],
                                 member_data: list | None = None,
                                 detail_list: list | None = None,
                                 show_detail: bool = False,
                                 net_income: float = 0.0,
                                 pl_grand_override: tuple[float, float, float] | None = None,
                                 sch_k_grand_override: float | None = None,
                                 elim_by_account: dict[tuple[str, str], float] | None = None,
                                 cte_by_account:  dict[tuple[str, str], float] | None = None,
                                 label_to_member_id: dict[str, str] | None = None):
        elim_by_account = elim_by_account or {}
        cte_by_account  = cte_by_account or {}
        label_to_member_id = label_to_member_id or {}
        N = self._NCOLS
        tree.clear()
        if not data:
            item = QTreeWidgetItem(["No data yet — add subsidiary binders."] + [""] * (N - 1))
            item.setFlags(Qt.ItemIsEnabled)
            item.setForeground(0, QBrush(QColor("#888")))
            tree.addTopLevelItem(item)
            return

        # Build per-member account detail lookup keyed by (member_label, section, line_name)
        # {member_label: {section: {line_name: [acct_dicts]}}}
        # Needed even when show_detail is off, to roll each tax line's own
        # elimination/CTE adjustment up from its accounts (see _line_adjustment).
        mem_acct_detail: dict = {}
        if detail_list:
            for mem_label, mem_det in detail_list:
                mem_acct_detail[mem_label] = mem_det

        group_names = {g["group_id"]: g["name"] for g in self._consol_groups}

        def _line_adjustment(section: str, line_name: str, by_account: dict) -> float:
            """Sum an account-level elim/cte dict over every account under this
            tax line, across all subsidiaries — gives the tax-line-level total
            without requiring "Show Account Detail" to be turned on."""
            total = 0.0
            for mem_label, mem_det in mem_acct_detail.items():
                member_id = label_to_member_id.get(mem_label)
                for acct in mem_det.get(section, {}).get(line_name, []):
                    total += by_account.get((member_id, acct.get("account_id")), 0.0)
            return total

        def _line_accounts(section: str, line_name: str) -> list[tuple[str, str, str]]:
            """(member_id, account_id, display label) for every account under
            this tax line — used to populate the right-click 'create entry for
            this account' menu directly from the statement preview."""
            out = []
            for mem_label, mem_det in mem_acct_detail.items():
                member_id = label_to_member_id.get(mem_label)
                for acct in mem_det.get(section, {}).get(line_name, []):
                    aid = acct.get("account_id")
                    if member_id and aid:
                        num = acct.get("number", "")
                        name = acct.get("name", "")
                        acct_label = f"{num}  {name}" if num else name
                        out.append((member_id, aid, f"{mem_label}: {acct_label}"))
            return out

        grand_combined = 0.0
        grand_elim     = 0.0

        def _sec_sort_key(item):
            _, lines = item
            return min(v["sort"] for v in lines.values()) // 1000 if lines else 999

        sec_bg = QBrush(QColor(_SECTION_BG))

        def _sec_match(section_name, by_section_map):
            # Exact (trimmed, case-insensitive) match only. The previous
            # prefix-based match ("A startswith B or B startswith A") let an
            # elimination line with a blank/unmapped section (key == "")
            # match EVERY section, since every string starts with "" —
            # silently multiplying that amount into every row's EJE/CTE
            # column and corrupting the balance check.
            sl = section_name.strip().lower()
            return sum(
                amt for key, amt in by_section_map.items()
                if key.strip() and key.strip().lower() == sl
            )

        grand_cte = 0.0

        # Gross Profit bridge (P&L only): Revenue minus COGS, injected right
        # after the last COGS-like section, GAAP-style — matching the
        # regular (non-consolidated) P&L view.
        is_pl = label != "Balance Sheet"
        gross_profit_injected = False
        rev_combined = rev_elim = rev_cte = 0.0
        cogs_combined = cogs_elim = cogs_cte = 0.0
        seen_revenue = False

        for section, lines in sorted(data.items(), key=_sec_sort_key):
            sec_combined = sum(v["final"] for v in lines.values())
            sec_elim = _sec_match(section, elim_by_section)
            sec_cte  = _sec_match(section, cte_by_section)
            sec_net  = sec_combined + sec_elim
            sec_tax  = sec_net + sec_cte

            grand_combined += sec_combined
            grand_elim     += sec_elim
            grand_cte      += sec_cte

            # ── Section header: label only, no amounts (GAAP style) ───────
            sec_item = QTreeWidgetItem([section] + [""] * (N - 1))
            sec_item.setFlags(Qt.ItemIsEnabled)
            sec_item.setFont(0, _bold())
            for c in range(N):
                sec_item.setBackground(c, sec_bg)
            tree.addTopLevelItem(sec_item)

            # ── Tax line children ─────────────────────────────────────────
            for line_name, vals in sorted(lines.items(), key=lambda x: x[1]["sort"]):
                combined_final = vals["final"]
                line_elim = _line_adjustment(section, line_name, elim_by_account)
                line_cte  = _line_adjustment(section, line_name, cte_by_account)
                line_net  = combined_final + line_elim
                line_tax  = line_net + line_cte
                child = QTreeWidgetItem([
                    "    " + line_name,
                    _fmt(combined_final),
                    _fmt(line_elim) if abs(line_elim) >= 0.005 else "",
                    _fmt(line_net),
                    _fmt(line_cte) if abs(line_cte) >= 0.005 else "",
                    _fmt(line_tax),
                ])
                child.setFlags(Qt.ItemIsEnabled)
                for c in (1, 3, 5):
                    child.setFont(c, _mono())
                    child.setTextAlignment(c, Qt.AlignRight | Qt.AlignVCenter)
                if abs(line_elim) >= 0.005:
                    child.setFont(2, _mono())
                    child.setTextAlignment(2, Qt.AlignRight | Qt.AlignVCenter)
                    child.setForeground(2, QBrush(QColor(_ELIM_FG)))
                if abs(line_cte) >= 0.005:
                    child.setFont(4, _mono())
                    child.setTextAlignment(4, Qt.AlignRight | Qt.AlignVCenter)
                    child.setForeground(4, QBrush(QColor(_PURPLE)))
                child.setData(0, Qt.UserRole, {
                    "kind": "line",
                    "accounts": _line_accounts(section, line_name),
                })
                sec_item.addChild(child)

                # ── Level 1 expand: per-subsidiary totals for this line ───
                if member_data:
                    for mem_label, mem_sdata in member_data:
                        mem_final = (mem_sdata.get(section, {})
                                               .get(line_name, {})
                                               .get("final", 0.0))
                        if abs(mem_final) < 0.005:
                            continue
                        sub_row = QTreeWidgetItem(
                            ["        " + mem_label, _fmt(mem_final)]
                            + [""] * (N - 2)
                        )
                        sub_row.setFlags(Qt.ItemIsEnabled)
                        sub_row.setFont(1, _mono())
                        sub_row.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
                        sub_row.setForeground(0, QBrush(QColor("#334466")))
                        sub_row.setData(0, Qt.UserRole, {
                            "kind": "line",
                            "accounts": [t for t in _line_accounts(section, line_name)
                                        if t[2].startswith(f"{mem_label}:")],
                        })
                        child.addChild(sub_row)

                        # ── Level 2 expand: individual accounts per sub ───
                        if show_detail:
                            accts = (mem_acct_detail.get(mem_label, {})
                                                    .get(section, {})
                                                    .get(line_name, []))
                            member_id = label_to_member_id.get(mem_label)
                            # Grouped accounts first (by group name), then ungrouped
                            def _group_key(acct):
                                gid = self._consol_group_members.get((member_id, acct.get("account_id")))
                                gname = group_names.get(gid, "") if gid else ""
                                return (gname == "", gname)
                            for acct in sorted(accts, key=_group_key):
                                num  = acct.get("number", "")
                                name = acct.get("name", "")
                                gid  = self._consol_group_members.get((member_id, acct.get("account_id")))
                                gname = group_names.get(gid) if gid else None
                                indent = "                " if gname else "            "
                                base_lbl = f"{num}  {name}" if num else name
                                lbl = f"{indent}{base_lbl}"
                                acct_final = acct["final"]
                                acct_key   = (member_id, acct.get("account_id"))
                                acct_elim  = elim_by_account.get(acct_key, 0.0)
                                acct_cte   = cte_by_account.get(acct_key, 0.0)
                                acct_net   = acct_final + acct_elim
                                acct_tax   = acct_net + acct_cte
                                a_row = QTreeWidgetItem([
                                    lbl, _fmt(acct_final),
                                    _fmt(acct_elim) if abs(acct_elim) >= 0.005 else "—",
                                    _fmt(acct_net),
                                    _fmt(acct_cte) if abs(acct_cte) >= 0.005 else "—",
                                    _fmt(acct_tax),
                                ])
                                a_row.setFlags(Qt.ItemIsEnabled)
                                muted = QBrush(QColor("#666666"))
                                for c in range(1, N):
                                    a_row.setFont(c, _mono())
                                    a_row.setTextAlignment(c, Qt.AlignRight | Qt.AlignVCenter)
                                    a_row.setForeground(c, muted)
                                a_row.setForeground(0, muted)
                                if gname:
                                    tint = QBrush(QColor("#EEF1F9"))
                                    for c in range(N):
                                        a_row.setBackground(c, tint)
                                    a_row.setToolTip(0, f"Group: {gname}")
                                if abs(acct_elim) >= 0.005:
                                    a_row.setForeground(2, QBrush(QColor(_ELIM_FG)))
                                if abs(acct_cte) >= 0.005:
                                    a_row.setForeground(4, QBrush(QColor(_PURPLE)))
                                if member_id:
                                    a_row.setData(0, Qt.UserRole, {
                                        "kind": "account",
                                        "member_id": member_id,
                                        "account_id": acct.get("account_id"),
                                        "label": f"{mem_label}: {num}  {name}" if num else f"{mem_label}: {name}",
                                    })
                                sub_row.addChild(a_row)

            sec_item.setExpanded(True)

            # ── Section total: always-visible top-level row (GAAP style) ──
            sec_total = QTreeWidgetItem([
                f"  Total {section}",
                _fmt(sec_combined),
                _fmt(sec_elim) if abs(sec_elim) >= 0.005 else "—",
                _fmt(sec_net),
                _fmt(sec_cte) if abs(sec_cte) >= 0.005 else "—",
                _fmt(sec_tax),
            ])
            sec_total.setFlags(Qt.ItemIsEnabled)
            sec_total.setFont(0, _bold())
            for c in range(1, N):
                sec_total.setFont(c, _mono_bold())
                sec_total.setTextAlignment(c, Qt.AlignRight | Qt.AlignVCenter)
            if abs(sec_elim) >= 0.005:
                sec_total.setForeground(2, QBrush(QColor(_ELIM_FG)))
            if abs(sec_cte) >= 0.005:
                sec_total.setForeground(4, QBrush(QColor(_PURPLE)))
            for c in range(N):
                sec_total.setBackground(c, sec_bg)
            tree.addTopLevelItem(sec_total)

            # Small gap between sections
            gap = QTreeWidgetItem([""] * N)
            gap.setFlags(Qt.NoItemFlags)
            gap.setData(0, Qt.SizeHintRole, QSize(0, 5))
            tree.addTopLevelItem(gap)

            if is_pl:
                # Category lives on the tax line, not the section label — use
                # the first line's stored category as the section's bucket.
                # (All lines in a section share one category by construction;
                # falls back to name-matching only for pre-migration data.)
                sec_category = (next(iter(lines.values()), {}).get("category")
                               or _classify_section("ProfitAndLoss", section))
                if sec_category == CATEGORY_SCHEDULE_K:
                    pass   # broken out separately below via raw-value math (see sch_k_breakdown)
                elif sec_category == CATEGORY_REVENUE:
                    rev_combined += sec_combined
                    rev_elim     += sec_elim
                    rev_cte      += sec_cte
                    seen_revenue = True
                elif sec_category == CATEGORY_COGS:
                    cogs_combined += sec_combined
                    cogs_elim     += sec_elim
                    cogs_cte      += sec_cte
                    if not gross_profit_injected and seen_revenue:
                        gp_combined = rev_combined - cogs_combined
                        gp_net      = (rev_combined + rev_elim) - (cogs_combined + cogs_elim)
                        gp_tax      = ((rev_combined + rev_elim + rev_cte)
                                       - (cogs_combined + cogs_elim + cogs_cte))
                        gp_row = QTreeWidgetItem([
                            "  Gross Profit",
                            _fmt(gp_combined),
                            _fmt(rev_elim - cogs_elim) if abs(rev_elim - cogs_elim) >= 0.005 else "—",
                            _fmt(gp_net),
                            _fmt(rev_cte - cogs_cte) if abs(rev_cte - cogs_cte) >= 0.005 else "—",
                            _fmt(gp_tax),
                        ])
                        gp_row.setFlags(Qt.ItemIsEnabled)
                        gp_row.setFont(0, _bold())
                        for c in range(1, N):
                            gp_row.setFont(c, _mono_bold())
                            gp_row.setTextAlignment(c, Qt.AlignRight | Qt.AlignVCenter)
                        gp_bg = QBrush(QColor("#E8ECF4"))
                        for c in range(N):
                            gp_row.setBackground(c, gp_bg)
                        tree.addTopLevelItem(gp_row)
                        gap2 = QTreeWidgetItem([""] * N)
                        gap2.setFlags(Qt.NoItemFlags)
                        gap2.setData(0, Qt.SizeHintRole, QSize(0, 6))
                        tree.addTopLevelItem(gap2)
                        gross_profit_injected = True

        is_bs = label == "Balance Sheet"

        # Net income hasn't closed to equity mid-engagement, so the raw BS
        # (Assets + Liabilities + Equity only) won't net to zero on its own —
        # show the bridge explicitly rather than silently folding it in.
        if is_bs and abs(net_income) >= 0.005:
            ni_row = QTreeWidgetItem(
                ["  Current Period Net Income (from P&L)"] + [""] * (N - 2) + [_fmt(net_income)]
            )
            ni_row.setFlags(Qt.ItemIsEnabled)
            ni_row.setFont(0, _bold())
            ni_row.setFont(N - 1, _mono_bold())
            ni_row.setTextAlignment(N - 1, Qt.AlignRight | Qt.AlignVCenter)
            ni_row.setForeground(0, QBrush(QColor("#555")))
            tree.addTopLevelItem(ni_row)
            gap2 = QTreeWidgetItem([""] * N)
            gap2.setFlags(Qt.NoItemFlags)
            gap2.setData(0, Qt.SizeHintRole, QSize(0, 5))
            tree.addTopLevelItem(gap2)

        if not is_bs and pl_grand_override is not None:
            # Revenue and expense-type sections are both displayed positive,
            # so summing every section's own total (grand_combined above)
            # overstates net income by adding expenses instead of subtracting
            # them. Use the correctly-signed net-income figure instead —
            # computed once in _refresh_combined from raw DR/CR values.
            grand_combined, grand_elim, grand_cte = pl_grand_override

        # Ordinary Business Income vs. Schedule K bridge — shown separately
        # so it's visible that each K item (some increase income, some
        # decrease it) nets correctly instead of being buried in one total.
        # Uses account-level raw DR/CR math (sch_k_grand_override), not a
        # per-section display sum — Schedule K sections mix income-type and
        # deduction-type accounts, so a blind sum would get some items'
        # signs backwards the same way the old whole-statement total did.
        if is_pl and sch_k_grand_override is not None:
            sch_k_ni = sch_k_grand_override
            total_ni = grand_combined + grand_elim + grand_cte
            obi_ni   = total_ni - sch_k_ni
            obi_row = QTreeWidgetItem(
                ["Ordinary Business Income / (Loss)"] + [""] * (N - 2) + [_fmt(obi_ni)]
            )
            obi_row.setFlags(Qt.ItemIsEnabled)
            obi_row.setFont(0, _bold())
            obi_row.setFont(N - 1, _mono_bold())
            obi_row.setTextAlignment(N - 1, Qt.AlignRight | Qt.AlignVCenter)
            tree.addTopLevelItem(obi_row)

            k_row = QTreeWidgetItem(
                ["+ Schedule K Items (Net)"] + [""] * (N - 2) + [_fmt(sch_k_ni)]
            )
            k_row.setFlags(Qt.ItemIsEnabled)
            k_row.setFont(N - 1, _mono())
            k_row.setTextAlignment(N - 1, Qt.AlignRight | Qt.AlignVCenter)
            tree.addTopLevelItem(k_row)

        # Rule
        rule = QTreeWidgetItem([""] * N)
        rule.setFlags(Qt.NoItemFlags)
        for c in range(N):
            rule.setBackground(c, QBrush(QColor("#999999")))
        rule.setData(0, Qt.SizeHintRole, QSize(0, 2))
        tree.addTopLevelItem(rule)

        grand_net = grand_combined + grand_elim + (net_income if is_bs else 0.0)
        grand_tax = grand_net + grand_cte
        gt_label = "Balance Check (net should be 0)" if is_bs else "Net Income / (Loss)"
        gt = QTreeWidgetItem([
            gt_label,
            _fmt(grand_combined),
            _fmt(grand_elim) if abs(grand_elim) >= 0.005 else "—",
            _fmt(grand_net),
            _fmt(grand_cte) if abs(grand_cte) >= 0.005 else "—",
            _fmt(grand_tax),
        ])
        gt.setFlags(Qt.ItemIsEnabled)
        gt.setFont(0, _bold())
        for c in range(1, N):
            gt.setFont(c, _mono_bold())
            gt.setTextAlignment(c, Qt.AlignRight | Qt.AlignVCenter)
        if is_bs:
            ok_color = QColor("#2A6A4A") if abs(grand_net) < 0.005 else QColor("#AA1111")
            gt.setForeground(3, QBrush(ok_color))
        if abs(grand_cte) >= 0.005:
            gt.setForeground(4, QBrush(QColor(_PURPLE)))
        tree.addTopLevelItem(gt)

    def _current_tree(self) -> QTreeWidget:
        idx = self._tabs.currentIndex()
        return self._pl_tree if idx == 2 else self._bs_tree

    def _on_toggle_expand(self):
        tree = self._current_tree()
        expanding = not self._btn_expand._expanded
        self._btn_expand._expanded = expanding
        self._apply_expand_state(tree, expanding)
        self._btn_expand.setText("⊟  Collapse All" if expanding else "⊞  Expand All")

    def _apply_expand_state(self, tree: QTreeWidget, expanded: bool):
        """Apply the current expand/collapse preference to a tree without changing button state."""
        if expanded:
            tree.expandAll()
        else:
            tree.collapseAll()
            for i in range(tree.topLevelItemCount()):
                item = tree.topLevelItem(i)
                if item and item.childCount() > 0:
                    item.setExpanded(True)

    def _reset_expand_btn(self):
        self._btn_expand._expanded = False
        self._btn_expand.setText("⊞  Expand All")

    def _apply_detail_toggle(self, checked: bool):
        """Re-render combined trees with or without account-level rows (no disk read)."""
        show = self._btn_detail.isChecked()
        elim_by_account = getattr(self, "_elim_by_account", {})
        cte_by_account  = getattr(self, "_cte_by_account", {})
        label_to_member_id = getattr(self, "_label_to_member_id", {})
        self._populate_combined_tree(
            self._bs_tree, self._combined_bs, "Balance Sheet",
            self._elim_by_section, self._cte_by_section,
            member_data=self._member_bs,
            detail_list=self._detail_bs, show_detail=show,
            net_income=getattr(self, "_combined_net_income", 0.0),
            elim_by_account=elim_by_account, cte_by_account=cte_by_account,
            label_to_member_id=label_to_member_id,
        )
        self._populate_combined_tree(
            self._pl_tree, self._combined_pl, "P&L",
            self._elim_by_section, self._cte_by_section,
            member_data=self._member_pl,
            detail_list=self._detail_pl, show_detail=show,
            pl_grand_override=getattr(self, "_pl_grand_override", None),
            sch_k_grand_override=getattr(self, "_sch_k_grand_override", None),
            elim_by_account=elim_by_account, cte_by_account=cte_by_account,
            label_to_member_id=label_to_member_id,
        )
        # Restore expand state after tree rebuild
        expanded = self._btn_expand._expanded
        self._apply_expand_state(self._bs_tree, expanded)
        self._apply_expand_state(self._pl_tree, expanded)

    def _on_export_pdf(self):
        """Export combined BS + P&L to a PDF."""
        entity = self._job.get("client_name", "Entity")
        year   = self._job.get("tax_year", "")
        safe   = entity.replace("/", "-").replace("\\", "-").strip() or "Consolidated"
        default_name = f"{safe} {year} Consolidated Financials.pdf"
        default_dir  = str(self._source_xlsx.parent) if self._source_xlsx else ""

        from pathlib import Path as _Path
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Consolidated Financials",
            str(_Path(default_dir) / default_name) if default_dir else default_name,
            "PDF Files (*.pdf)",
        )
        if not filename:
            return

        from PySide6.QtGui import QTextDocument, QPageLayout, QPageSize
        from PySide6.QtPrintSupport import QPrinter
        from PySide6.QtCore import QMarginsF

        printer = QPrinter(QPrinter.HighResolution)
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(filename)
        printer.setPageLayout(QPageLayout(
            QPageSize(QPageSize.PageSizeId.Letter),
            QPageLayout.Orientation.Landscape,
            QMarginsF(54, 54, 54, 54),
        ))

        html = self._build_consolidated_html(entity, year)
        doc = QTextDocument()
        doc.setHtml(html)
        doc.print_(printer)
        QMessageBox.information(self, "Export Complete", f"Saved to:\n{filename}")

    def _build_consolidated_html(self, entity: str, year) -> str:
        import html as _html
        import datetime as _dt

        style = """
        body { font-family: 'Segoe UI', Arial, sans-serif; font-size: 10pt; color: #000; }
        h1 { font-size: 14pt; color: #1A2B4C; text-align: center; margin-bottom: 4px; }
        .sub { text-align: center; font-size: 9pt; color: #666; margin-bottom: 16px; }
        h2 { font-size: 11pt; color: #1A2B4C; margin-top: 24px; margin-bottom: 6px;
             border-bottom: 2px solid #1A2B4C; padding-bottom: 3px; }
        table { width: 100%; border-collapse: collapse; margin-bottom: 16px; }
        th { background: #1A2B4C; color: white; font-size: 9pt; padding: 4px 10px; }
        th.left { text-align: left; }
        th.right { text-align: right; }
        tr.sec td { background: #F2F4F6; font-weight: bold; padding: 4px 10px; }
        tr.line td { padding: 3px 10px 3px 28px; font-size: 9pt; }
        tr.total td { background: #F2F4F6; font-weight: bold; padding: 4px 10px;
                      border-top: 2px solid #888; }
        td.num { text-align: right; font-family: Consolas, monospace; }
        """

        def _sec_sort(sec_lines: dict) -> int:
            return min(v["sort"] for v in sec_lines.values()) // 1000 if sec_lines else 999

        def _build_table(title: str, data: "SectionData", stmt_label: str, is_bs: bool) -> str:
            rows = ""
            grand = 0.0
            for section, lines in sorted(data.items(), key=lambda kv: _sec_sort(kv[1])):
                sec_total = sum(v["final"] for v in lines.values())
                if is_bs:
                    grand += sec_total
                else:
                    # Revenue and expense sections are BOTH displayed positive
                    # (so "Total Deductions" reads as a positive dollar
                    # figure) — summing them would add expenses instead of
                    # subtracting them. -sum(raw) self-cancels correctly.
                    grand += -sum(v.get("raw", v["final"]) for v in lines.values())
                rows += (f'<tr class="sec"><td>{_html.escape(section)}</td>'
                         f'<td class="num">{_fmt(sec_total)}</td></tr>')
                for lname, vals in sorted(lines.items(), key=lambda x: x[1]["sort"]):
                    rows += (f'<tr class="line"><td>{_html.escape(lname)}</td>'
                             f'<td class="num">{_fmt(vals["final"])}</td></tr>')
            total_label = "Balance Check (should be 0)" if is_bs else "Net Income / (Loss)"
            rows += (f'<tr class="total"><td><b>{_html.escape(total_label)}</b></td>'
                     f'<td class="num"><b>{_fmt(grand)}</b></td></tr>')
            return (f'<h2>{_html.escape(title)}</h2>'
                    f'<table><thead><tr>'
                    f'<th class="left">Section / Account</th>'
                    f'<th class="right">Combined FINAL</th>'
                    f'</tr></thead><tbody>{rows}</tbody></table>')

        today = _dt.date.today().strftime("%B %d, %Y")
        body = (f'<h1>{_html.escape(entity)} — Consolidated Financial Statements</h1>'
                f'<p class="sub">Tax Year {year} &nbsp;&bull;&nbsp; Prepared {today}</p>')
        body += _build_table("Combined Balance Sheet", self._combined_bs, "Balance Sheet", is_bs=True)
        body += _build_table("Combined Profit & Loss", self._combined_pl, "Profit & Loss", is_bs=False)
        return f'<html><head><style>{style}</style></head><body>{body}</body></html>'

    def _on_tab_changed(self, idx: int):
        if idx in (1, 2):   # only reset expand when switching to a financial tree tab
            self._reset_expand_btn()
        if idx == 3:   # Consolidation Summary — rebuild to pick up any EJE changes
            self._refresh_combined()
        if idx == 4:   # Notes — refresh to pick up any new notes
            if hasattr(self._notes_dock_ref, "refresh"):
                self._notes_dock_ref.refresh()

    def _on_toggle_entry_panel(self):
        """Collapse or restore the entry editor within the splitter."""
        sizes = self._main_splitter.sizes()
        if not sizes:
            return
        _WRAPPER_HDR_H = 28
        if sizes[-1] > _WRAPPER_HDR_H + 4:
            self._entry_last_height = sizes[-1]
            total = sum(sizes)
            self._entry_panel.setVisible(False)
            self._main_splitter.setSizes([total - _WRAPPER_HDR_H, _WRAPPER_HDR_H])
            self._entry_hide_btn.setText("▲  Show")
        else:
            restored = getattr(self, "_entry_last_height", 260)
            total = sum(sizes)
            self._entry_panel.setVisible(True)
            self._main_splitter.setSizes([total - restored, restored])
            self._entry_hide_btn.setText("▼  Hide")

    def _on_save(self):
        if not self._source_xlsx:
            return
        if getattr(self, "_saving", False):
            return   # a save is already in flight — a second one could
                      # interleave its write with the first and corrupt both
        self._saving = True
        self._save_btn.setEnabled(False)
        from atbworkup.exporter.review_package import save_workup
        try:
            with db_connection(self._path) as conn:
                save_workup(conn, job=self._job, output_path=self._source_xlsx,
                            performed_by=self._performed_by)
            # Confirm the file we just wrote is actually openable before
            # declaring success — catches a corrupted save immediately
            # instead of the next time someone opens it.
            import zipfile
            with zipfile.ZipFile(self._source_xlsx) as z:
                bad_entry = z.testzip()
            if bad_entry is not None:
                raise RuntimeError(
                    f"the saved file failed its own integrity check (bad entry: {bad_entry})"
                )
            self.statusBar().showMessage(f"Saved — {self._source_xlsx}")
        except Exception as exc:
            QMessageBox.critical(self, "Save Error", str(exc))
        finally:
            self._saving = False
            self._save_btn.setEnabled(True)

    def closeEvent(self, event):
        self._on_save()
        if self._path.exists():
            try:
                self._path.unlink()
            except Exception:
                pass
        event.accept()


# ── Consolidation Summary widget ──────────────────────────────────────────────

class _SummaryWidget(QWidget):
    """
    Cross-tab summary: rows = major sections, cols = one per subsidiary (FINAL)
    + Combined + EJEs + Net Consolidated.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(8, 8, 8, 8)

        self._note = QLabel(
            "Add subsidiary binders and click Recalculate to populate the summary."
        )
        self._note.setStyleSheet("font-size: 11px; color: #666;")
        self._layout.addWidget(self._note)

        self._tree = QTreeWidget()
        self._tree.setVisible(False)
        self._layout.addWidget(self._tree)

    def rebuild(self, member_names: list[str],
                member_bs: list[tuple[str, SectionData]],
                member_pl: list[tuple[str, SectionData]],
                combined_bs: SectionData,
                combined_pl: SectionData,
                elim_total: float,
                cte_total: float = 0.0,
                pl_net_income_base: float | None = None,
                pl_elim_ni: float | None = None,
                pl_cte_ni: float | None = None):
        if not member_names:
            self._note.setVisible(True)
            self._tree.setVisible(False)
            return

        self._note.setVisible(False)
        self._tree.setVisible(True)
        self._tree.clear()

        # Dynamic columns: Section/Line | Sub1 | Sub2 | ... | Combined | EJEs | Net Consolidated | Tax Entries | Net Tax
        n_subs = len(member_names)
        cols = (["Section / Tax Line"] + member_names
                + ["Combined", "Eliminations", "Net Consolidated", "Tax Entries (CTE)", "Net Tax"])
        self._tree.setColumnCount(len(cols))
        self._tree.setHeaderLabels(cols)
        hdr = self._tree.header()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, len(cols)):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hdr.setDefaultAlignment(Qt.AlignRight | Qt.AlignVCenter)
        hdr.setStyleSheet(
            f"QHeaderView::section {{ background: {_NAVY}; color: white; "
            "font-size: 11px; font-weight: bold; padding: 4px 6px; border: none; "
            "border-right: 1px solid #2A3B5C; }}"
        )

        def _sec_sort(sec: str, combined: SectionData) -> int:
            if sec in combined and combined[sec]:
                return min(v["sort"] for v in combined[sec].values()) // 1000
            return 999

        def _sorted_sections(data_list, combined):
            all_secs = {sec for _, bd in data_list for sec in bd} | set(combined.keys())
            return sorted(all_secs, key=lambda s: _sec_sort(s, combined))

        all_bs_sections = _sorted_sections(member_bs, combined_bs)
        all_pl_sections = _sorted_sections(member_pl, combined_pl)

        def _member_section_total(data_list, section, name):
            for mname, sdata in data_list:
                if mname == name and section in sdata:
                    return sum(v["final"] for v in sdata[section].values())
            return 0.0

        def _member_line_total(data_list, section, lname, name):
            for mname, sdata in data_list:
                if mname == name and section in sdata and lname in sdata[section]:
                    return sdata[section][lname]["final"]
            return 0.0

        def _combined_section_total(combined, section):
            return sum(v["final"] for v in combined.get(section, {}).values())

        def _member_net_income(pl_sdata: SectionData) -> float:
            # Same raw-based rule as the combined figure: revenue/expense
            # sections both display positive, so summing them overstates
            # net income. -sum(raw) self-cancels correctly.
            return -sum(v.get("raw", v["final"])
                       for lines in pl_sdata.values() for v in lines.values())

        def _add_group(group_label, sections, data_list, combined, elim, cte,
                       combined_override: float | None = None):
            # ── Group header ─────────────────────────────────────────────
            g_item = QTreeWidgetItem([group_label] + [""] * (n_subs + 5))
            g_item.setFlags(Qt.ItemIsEnabled)
            g_item.setFont(0, _bold())
            bg_grp = QBrush(QColor("#E5EAF3"))
            for c in range(len(cols)):
                g_item.setBackground(c, bg_grp)
            self._tree.addTopLevelItem(g_item)

            grp_subs = [0.0] * n_subs
            grp_comb = 0.0

            bg_sec = QBrush(QColor(_SECTION_BG))

            for section in sections:
                sub_vals = [_member_section_total(data_list, section, nm)
                            for nm in member_names]
                comb_val = _combined_section_total(combined, section)

                # Section header — label only, no amounts (GAAP style)
                sec_item = QTreeWidgetItem(
                    [section] + [""] * (n_subs + 5)
                )
                sec_item.setFlags(Qt.ItemIsEnabled)
                sec_item.setFont(0, _bold())
                for c in range(len(cols)):
                    sec_item.setBackground(c, bg_sec)
                g_item.addChild(sec_item)

                # Tax line children
                if section in combined:
                    for lname, lvals in sorted(
                        combined[section].items(), key=lambda x: x[1]["sort"]
                    ):
                        line_subs = [_member_line_total(data_list, section, lname, nm)
                                     for nm in member_names]
                        l_item = QTreeWidgetItem(
                            ["    " + lname]
                            + [_fmt(v) for v in line_subs]
                            + [_fmt(lvals["final"]), "—", _fmt(lvals["final"]), "—", _fmt(lvals["final"])]
                        )
                        l_item.setFlags(Qt.ItemIsEnabled)
                        for c in range(1, len(cols)):
                            l_item.setFont(c, _mono())
                            l_item.setTextAlignment(c, Qt.AlignRight | Qt.AlignVCenter)
                        sec_item.addChild(l_item)

                # Section total — last child, bold with amounts
                sec_tot = QTreeWidgetItem(
                    [f"  Total {section}"]
                    + [_fmt(v) for v in sub_vals]
                    + [_fmt(comb_val), "—", _fmt(comb_val), "—", _fmt(comb_val)]
                )
                sec_tot.setFlags(Qt.ItemIsEnabled)
                for c in range(len(cols)):
                    sec_tot.setBackground(c, bg_sec)
                    sec_tot.setFont(c, _mono_bold())
                for c in range(1, len(cols)):
                    sec_tot.setTextAlignment(c, Qt.AlignRight | Qt.AlignVCenter)
                sec_item.addChild(sec_tot)
                sec_item.setExpanded(False)  # collapsed by default

                for i, v in enumerate(sub_vals):
                    grp_subs[i] += v
                grp_comb += comb_val

            g_item.setExpanded(True)

            # ── Group total — top-level so always visible ─────────────────
            if combined_override is not None:
                # Revenue/expense sections both display positive, so summing
                # them (grp_comb above) overstates net income. Use the
                # correctly-signed figure computed from raw DR/CR values —
                # both for the combined column and each subsidiary's own.
                grp_comb = combined_override
                grp_subs = [_member_net_income(sdata) for _, sdata in data_list]
            grp_elim = elim if group_label == "P&L" else 0.0
            grp_cte  = cte  if group_label == "P&L" else 0.0
            grp_net  = grp_comb + grp_elim
            grp_tax  = grp_net + grp_cte
            total_row = QTreeWidgetItem(
                [f"  Total {group_label}"]
                + [_fmt(v) for v in grp_subs]
                + [_fmt(grp_comb),
                   _fmt(grp_elim) if abs(grp_elim) >= 0.005 else "—",
                   _fmt(grp_net),
                   _fmt(grp_cte) if abs(grp_cte) >= 0.005 else "—",
                   _fmt(grp_tax)]
            )
            total_row.setFlags(Qt.ItemIsEnabled)
            total_row.setFont(0, _bold())
            bg_tot = QBrush(QColor("#D8DFF0"))
            for c in range(len(cols)):
                total_row.setBackground(c, bg_tot)
                total_row.setFont(c, _mono_bold())
            for c in range(1, len(cols)):
                total_row.setTextAlignment(c, Qt.AlignRight | Qt.AlignVCenter)
            self._tree.addTopLevelItem(total_row)
            return grp_subs, grp_comb

        bs_subs, bs_comb = _add_group("Balance Sheet", all_bs_sections,
                                       member_bs, combined_bs, 0.0, 0.0)
        pl_subs, pl_comb = _add_group(
            "P&L", all_pl_sections, member_pl, combined_pl,
            elim=pl_elim_ni if pl_elim_ni is not None else elim_total,
            cte=pl_cte_ni if pl_cte_ni is not None else cte_total,
            combined_override=pl_net_income_base,
        )

        # ── Rule ──────────────────────────────────────────────────────────
        rule = QTreeWidgetItem([""] * len(cols))
        rule.setFlags(Qt.NoItemFlags)
        for c in range(len(cols)):
            rule.setBackground(c, QBrush(QColor("#999")))
        rule.setData(0, Qt.SizeHintRole, QSize(0, 2))
        self._tree.addTopLevelItem(rule)

        # ── Net Consolidated ──────────────────────────────────────────────
        all_sub_total = [a + b for a, b in zip(bs_subs, pl_subs)]
        all_comb = bs_comb + pl_comb
        all_net  = all_comb + elim_total
        all_tax  = all_net + cte_total
        overall = QTreeWidgetItem(
            ["Net Consolidated"]
            + [_fmt(v) for v in all_sub_total]
            + [_fmt(all_comb),
               _fmt(elim_total) if abs(elim_total) >= 0.005 else "—",
               _fmt(all_net),
               _fmt(cte_total) if abs(cte_total) >= 0.005 else "—",
               _fmt(all_tax)]
        )
        overall.setFlags(Qt.ItemIsEnabled)
        overall.setFont(0, _bold())
        bg_net = QBrush(QColor("#C8D4EE"))
        for c in range(len(cols)):
            overall.setBackground(c, bg_net)
            overall.setFont(c, _mono_bold())
        for c in range(1, len(cols)):
            overall.setTextAlignment(c, Qt.AlignRight | Qt.AlignVCenter)
        self._tree.addTopLevelItem(overall)


# ── Account-level entry editor (EJE / CTE with real DR/CR lines) ──────────────

class _ConsolAccountCombo(QComboBox):
    """
    Editable combo listing every subsidiary's accounts, one flat searchable
    list. Display: "CODE  1000  Cash — Operating". Selecting an item yields
    (member_id, account_id) via current_selection().
    """

    def __init__(self, items: list[dict], parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.setFocusPolicy(Qt.StrongFocus)
        self.lineEdit().setPlaceholderText("Subsidiary / account…")
        self._items = items
        self._build(items)

    def _build(self, items: list[dict]):
        self._by_display: dict[str, tuple[str, str]] = {}
        self.clear()
        self.addItem("", None)
        displays = []
        for it in items:
            num = (it.get("number") or "").strip()
            display = f"{it['member_label']}  {num}  {it['name']}".strip()
            displays.append(display)
            self._by_display[display] = (it["member_id"], it["account_id"])
            self.addItem(display, (it["member_id"], it["account_id"]))
        completer = QCompleter(displays, self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        self.setCompleter(completer)
        completer.activated.connect(self._on_completion_chosen)

    def refresh_items(self, items: list[dict]):
        current = self.current_selection()
        self._items = items
        self._build(items)
        if current:
            self.set_selection(*current)

    def _on_completion_chosen(self, text: str):
        idx = self.findText(text)
        if idx >= 0:
            self.setCurrentIndex(idx)

    def current_selection(self) -> tuple[str, str] | None:
        idx = self.currentIndex()
        return self.itemData(idx) if idx >= 0 else None

    def set_selection(self, member_id: str, account_id: str):
        for i in range(self.count()):
            data = self.itemData(i)
            if data and data[0] == member_id and data[1] == account_id:
                self.setCurrentIndex(i)
                return


class _ConsolMemoEdit(QLineEdit):
    """Memo field whose Tab either advances to the next row or adds a new
    blank line — matches the regular JE panel's tab-to-new-line behavior."""

    tab_pressed = Signal()

    def focusNextPrevChild(self, next: bool) -> bool:
        if next:
            self.tab_pressed.emit()
            return True
        return super().focusNextPrevChild(next)


class _ConsolAmountEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.setPlaceholderText("0.00")

    def wheelEvent(self, event):
        event.ignore()


def _parse_consol_amount(text: str) -> float:
    text = (text or "").strip().replace(",", "").replace("(", "-").replace(")", "")
    if not text:
        return 0.0
    try:
        return round(float(text), 2)
    except ValueError:
        return 0.0


class _ConsolGroupPickerDialog(QDialog):
    """Pick an existing consolidated account group, or create a new one."""

    def __init__(self, groups: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add to Group")
        self.setMinimumWidth(320)
        self._selected_group_id: str | None = None

        lo = QVBoxLayout(self)
        lo.addWidget(QLabel("Existing groups:"))
        self._list = QListWidget()
        for g in groups:
            item = QListWidgetItem(g["name"])
            item.setData(Qt.UserRole, g["group_id"])
            self._list.addItem(item)
        self._list.itemSelectionChanged.connect(self._on_list_selected)
        lo.addWidget(self._list)

        lo.addWidget(QLabel("— or create a new group —"))
        self._new_name = QLineEdit()
        self._new_name.setPlaceholderText("New group name…")
        self._new_name.textChanged.connect(self._on_new_name_changed)
        lo.addWidget(self._new_name)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        self._ok_btn = btns.button(QDialogButtonBox.Ok)
        self._ok_btn.setEnabled(False)
        lo.addWidget(btns)

    def _on_list_selected(self):
        items = self._list.selectedItems()
        if items:
            self._new_name.blockSignals(True)
            self._new_name.clear()
            self._new_name.blockSignals(False)
        self._ok_btn.setEnabled(bool(items) or bool(self._new_name.text().strip()))

    def _on_new_name_changed(self, text: str):
        if text.strip():
            self._list.blockSignals(True)
            self._list.clearSelection()
            self._list.blockSignals(False)
        self._ok_btn.setEnabled(bool(text.strip()) or bool(self._list.selectedItems()))

    def selected_group_id(self) -> str | None:
        items = self._list.selectedItems()
        return items[0].data(Qt.UserRole) if items else None

    def new_group_name(self) -> str:
        return self._new_name.text().strip()


_CE_COL_ACCT = 0
_CE_COL_DR   = 1
_CE_COL_CR   = 2
_CE_COL_MEMO = 3
_CE_COL_DEL  = 4


class _ConsolEntryEditor(QWidget):
    """
    Account-level eliminating/CTE entry editor: entry list on the left,
    line editor (Account / DR / CR / Memo) on the right — mirrors the
    regular JE panel's UX, but each line targets a specific subsidiary's
    account via consolidation_entry_lines(member_id, account_id).
    """

    changed = Signal()

    def __init__(self, path: Path, job_id: str, workpaper: str = "elim", parent=None):
        super().__init__(parent)
        self._path            = path
        self._job_id          = job_id
        self._workpaper       = workpaper
        self._current_entry_id: str | None = None
        self._account_items: list[dict] = []   # flattened across all members
        self._build_ui()

    def set_members(self, members: list[dict]):
        """members: [{"member_id","label","file_path"}] — called by the owner
        whenever the subsidiary list changes, to refresh account pickers."""
        items = []
        for m in members:
            fp = Path(m["file_path"])
            if not fp.exists():
                continue
            try:
                idx = _read_member_account_index(fp)
            except Exception:
                continue
            for aid, meta in idx.items():
                items.append({
                    "member_id":    m["member_id"],
                    "member_label": m["label"],
                    "account_id":   aid,
                    "number":       meta["number"],
                    "name":         meta["name"],
                })
        self._account_items = items
        for r in range(self._lines_table.rowCount()):
            combo = self._lines_table.cellWidget(r, _CE_COL_ACCT)
            if isinstance(combo, _ConsolAccountCombo):
                combo.refresh_items(items)

    def _build_ui(self):
        lo = QHBoxLayout(self)
        lo.setContentsMargins(8, 8, 8, 8)
        lo.setSpacing(8)

        # ── Left: entry list ─────────────────────────────────────────────
        left = QWidget()
        left.setFixedWidth(200)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        lbl = "EJE" if self._workpaper == "elim" else "CTE"
        btn_new = QPushButton(f"+ New {lbl}")
        btn_new.setStyleSheet(_BTN_NAVY)
        btn_new.clicked.connect(self._on_new_entry)
        ll.addWidget(btn_new)
        self._list = QTableWidget(0, 2)
        self._list.setHorizontalHeaderLabels(["#", "Description"])
        self._list.verticalHeader().setVisible(False)
        self._list.horizontalHeader().setStyleSheet(_HDR_STYLE)
        self._list.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._list.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._list.cellClicked.connect(self._on_list_select)
        ll.addWidget(self._list, 1)
        lo.addWidget(left)

        # ── Right: editor ─────────────────────────────────────────────────
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)

        top_row = QHBoxLayout()
        self._number_lbl = QLabel("—")
        self._number_lbl.setStyleSheet("font-weight: bold; color: #1A2B4C;")
        top_row.addWidget(self._number_lbl)
        self._desc = QLineEdit()
        self._desc.setPlaceholderText("Description…")
        top_row.addWidget(self._desc, 1)
        rl.addLayout(top_row)

        self._lines_table = QTableWidget(0, 5)
        self._lines_table.setHorizontalHeaderLabels(
            ["Subsidiary / Account", "DR", "CR", "Memo", ""]
        )
        self._lines_table.verticalHeader().setVisible(False)
        self._lines_table.setSelectionMode(QAbstractItemView.NoSelection)
        self._lines_table.setFocusPolicy(Qt.NoFocus)
        hh = self._lines_table.horizontalHeader()
        hh.setStyleSheet(_HDR_STYLE)
        hh.setSectionResizeMode(_CE_COL_ACCT, QHeaderView.Stretch)
        for c in (_CE_COL_DR, _CE_COL_CR):
            hh.setSectionResizeMode(c, QHeaderView.Fixed)
            self._lines_table.setColumnWidth(c, 100)
        hh.setSectionResizeMode(_CE_COL_MEMO, QHeaderView.Stretch)
        hh.setSectionResizeMode(_CE_COL_DEL, QHeaderView.Fixed)
        self._lines_table.setColumnWidth(_CE_COL_DEL, 28)
        rl.addWidget(self._lines_table, 1)

        bottom_row = QHBoxLayout()
        self._balance_lbl = QLabel("Balance: —")
        self._balance_lbl.setStyleSheet("font-weight: bold;")
        bottom_row.addWidget(self._balance_lbl)
        bottom_row.addStretch()
        self._save_btn = QPushButton("Save Entry")
        self._save_btn.setStyleSheet(_BTN_NAVY)
        self._save_btn.clicked.connect(self._on_save)
        self._save_btn.setEnabled(False)
        bottom_row.addWidget(self._save_btn)
        self._delete_btn = QPushButton("Delete Entry")
        self._delete_btn.setStyleSheet(_BTN)
        self._delete_btn.clicked.connect(self._on_delete)
        self._delete_btn.setEnabled(False)
        bottom_row.addWidget(self._delete_btn)
        rl.addLayout(bottom_row)

        lo.addWidget(right, 1)
        self._set_editor_enabled(False)

    # ── List ─────────────────────────────────────────────────────────────

    def refresh(self):
        self._list.setRowCount(0)
        with db_connection(self._path) as conn:
            entries = ce_model.get_entries(conn, self._job_id, self._workpaper)
        for e in entries:
            r = self._list.rowCount()
            self._list.insertRow(r)
            num_item = QTableWidgetItem(e["entry_number"])
            num_item.setData(Qt.UserRole, e["entry_id"])
            self._list.setItem(r, 0, num_item)
            self._list.setItem(r, 1, QTableWidgetItem(e.get("description", "")))

    def _on_list_select(self, row: int, *_):
        entry_id = self._list.item(row, 0).data(Qt.UserRole)
        if entry_id:
            self._load_entry(entry_id)

    def _select_entry_in_list(self, entry_id: str | None):
        if not entry_id:
            return
        for r in range(self._list.rowCount()):
            item = self._list.item(r, 0)
            if item and item.data(Qt.UserRole) == entry_id:
                self._list.selectRow(r)
                return

    # ── Editor rows ──────────────────────────────────────────────────────

    def _append_line_row(self, member_id: str | None = None,
                         account_id: str | None = None,
                         amount: float = 0.0, memo: str = ""):
        r = self._lines_table.rowCount()
        self._lines_table.insertRow(r)
        self._lines_table.setRowHeight(r, 28)

        combo = _ConsolAccountCombo(self._account_items)
        if member_id and account_id:
            combo.set_selection(member_id, account_id)
        combo.currentIndexChanged.connect(self._update_balance)
        self._lines_table.setCellWidget(r, _CE_COL_ACCT, combo)

        dr = _ConsolAmountEdit()
        cr = _ConsolAmountEdit()
        if amount > 0:
            dr.setText(f"{amount:.2f}")
        elif amount < 0:
            cr.setText(f"{abs(amount):.2f}")
        dr.textChanged.connect(self._update_balance)
        cr.textChanged.connect(self._update_balance)
        self._lines_table.setCellWidget(r, _CE_COL_DR, dr)
        self._lines_table.setCellWidget(r, _CE_COL_CR, cr)

        memo_edit = _ConsolMemoEdit()
        memo_edit.setText(memo)
        memo_edit._row = r
        memo_edit.tab_pressed.connect(lambda w=memo_edit: self._on_memo_tab(w))
        self._lines_table.setCellWidget(r, _CE_COL_MEMO, memo_edit)

        del_btn = QPushButton("×")
        del_btn.setFixedSize(24, 24)
        del_btn.setFocusPolicy(Qt.NoFocus)
        del_btn.setStyleSheet(
            "background: transparent; color: #C62828; font-weight: bold; border: none;"
        )
        del_btn.clicked.connect(lambda _=False, row=r: self._remove_line_row(row))
        self._lines_table.setCellWidget(r, _CE_COL_DEL, del_btn)

        QWidget.setTabOrder(combo, dr)
        QWidget.setTabOrder(dr, cr)
        QWidget.setTabOrder(cr, memo_edit)

    def _on_memo_tab(self, memo_widget: "_ConsolMemoEdit"):
        row = memo_widget._row
        if row == self._lines_table.rowCount() - 1:
            self._add_blank_line()
        next_combo = self._lines_table.cellWidget(row + 1, _CE_COL_ACCT)
        if next_combo:
            next_combo.setFocus()
            next_combo.lineEdit().selectAll()

    def _add_blank_line(self):
        self._append_line_row()

    def _remove_line_row(self, row: int):
        self._lines_table.removeRow(row)
        for r in range(self._lines_table.rowCount()):
            btn = self._lines_table.cellWidget(r, _CE_COL_DEL)
            if btn:
                try:
                    btn.clicked.disconnect()
                except RuntimeError:
                    pass
                btn.clicked.connect(lambda _=False, rr=r: self._remove_line_row(rr))
            memo = self._lines_table.cellWidget(r, _CE_COL_MEMO)
            if isinstance(memo, _ConsolMemoEdit):
                memo._row = r
        self._update_balance()

    def _collect_lines(self) -> list[dict]:
        lines = []
        for r in range(self._lines_table.rowCount()):
            combo = self._lines_table.cellWidget(r, _CE_COL_ACCT)
            dr_w  = self._lines_table.cellWidget(r, _CE_COL_DR)
            cr_w  = self._lines_table.cellWidget(r, _CE_COL_CR)
            memo_w = self._lines_table.cellWidget(r, _CE_COL_MEMO)
            if not isinstance(combo, _ConsolAccountCombo):
                continue
            sel = combo.current_selection()
            if not sel:
                continue
            member_id, account_id = sel
            dr = _parse_consol_amount(dr_w.text() if dr_w else "")
            cr = _parse_consol_amount(cr_w.text() if cr_w else "")
            amount = round(dr - cr, 2)
            memo = memo_w.text() if memo_w else ""
            lines.append({
                "member_id": member_id, "account_id": account_id,
                "amount": amount, "memo": memo,
            })
        return lines

    def _update_balance(self, *_):
        lines = self._collect_lines()
        total = ce_model.entry_balance(lines)
        balanced = abs(total) < 0.005
        if balanced:
            self._balance_lbl.setText("Balance: —  ✓")
            self._balance_lbl.setStyleSheet("font-weight: bold; color: #2e7d32;")
        else:
            self._balance_lbl.setText(f"Balance: {total:+,.2f}  ✗")
            self._balance_lbl.setStyleSheet("font-weight: bold; color: #C62828;")
        self._save_btn.setEnabled(balanced and bool(lines))

    def _set_editor_enabled(self, enabled: bool):
        self._desc.setEnabled(enabled)
        self._lines_table.setEnabled(enabled)
        if enabled:
            self._update_balance()   # recompute rather than blindly disabling Save
        else:
            self._save_btn.setEnabled(False)
        self._delete_btn.setEnabled(enabled and self._current_entry_id is not None)

    # ── New / load / save / delete ───────────────────────────────────────

    def _on_new_entry(self):
        self._current_entry_id = None
        with db_connection(self._path) as conn:
            number = ce_model.next_entry_number(conn, self._job_id, self._workpaper)
        self._number_lbl.setText(f"{number}  (unsaved)")
        self._desc.clear()
        self._lines_table.setRowCount(0)
        self._add_blank_line()
        self._set_editor_enabled(True)
        self._update_balance()
        self._list.clearSelection()
        self._desc.setFocus()

    def _load_entry(self, entry_id: str):
        with db_connection(self._path) as conn:
            entry = ce_model.get_entry(conn, entry_id)
            lines = ce_model.get_lines(conn, entry_id)
        if not entry:
            return
        self._current_entry_id = entry_id
        self._number_lbl.setText(entry["entry_number"])
        self._desc.setText(entry.get("description", ""))
        self._lines_table.setRowCount(0)
        for ln in lines:
            self._append_line_row(
                member_id=ln["member_id"], account_id=ln["account_id"],
                amount=ln.get("amount", 0.0), memo=ln.get("memo") or "",
            )
        self._add_blank_line()
        self._set_editor_enabled(True)
        self._update_balance()

    def _on_save(self):
        lines = self._collect_lines()
        if not lines:
            return
        description = self._desc.text().strip() or ("Eliminating Entry" if self._workpaper == "elim" else "Tax Entry")
        with db_connection(self._path) as conn:
            if self._current_entry_id:
                ce_model.update_entry(conn, self._current_entry_id, description=description)
                ce_model.save_lines(conn, self._current_entry_id, lines)
            else:
                entry = ce_model.create_entry(
                    conn, job_id=self._job_id, workpaper=self._workpaper,
                    description=description, originated_by="",
                )
                self._current_entry_id = entry["entry_id"]
                ce_model.save_lines(conn, self._current_entry_id, lines)
        self.refresh()
        self._select_entry_in_list(self._current_entry_id)
        self._delete_btn.setEnabled(True)
        self.changed.emit()

    def _on_delete(self):
        if not self._current_entry_id:
            return
        reply = QMessageBox.question(
            self, "Delete Entry", "Delete this entry and all its lines?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        with db_connection(self._path) as conn:
            ce_model.delete_entry(conn, self._current_entry_id)
        self._current_entry_id = None
        self.refresh()
        self._lines_table.setRowCount(0)
        self._desc.clear()
        self._number_lbl.setText("—")
        self._set_editor_enabled(False)
        self.changed.emit()


# ── Eliminations widget (legacy — section-level flat entries) ─────────────────
# Kept fully functional so binders with entries created before the account-level
# editor above still open and remain editable; new entries should use the
# account-level editor. Its totals still feed the combined BS/PL math.

class _EliminationsWidget(QWidget):
    """Simple table for entering eliminating or consolidated tax entries."""

    changed = Signal()   # emitted after any add / remove / edit

    def __init__(self, path: Path, job_id: str, workpaper: str = "elim", parent=None):
        super().__init__(parent)
        self._path      = path
        self._job_id    = job_id
        self._workpaper = workpaper
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)

        if self._workpaper == "elim":
            note_txt = (
                "Enter intercompany eliminating entries. Positive = debit, negative = credit. "
                "'Section / Line' associates the amount with a BS or P&L section for the "
                "EJEs column in the combined views."
            )
        else:
            note_txt = (
                "Enter consolidated-level tax entries (book-to-tax adjustments). "
                "Positive = debit, negative = credit. "
                "'Section / Line' associates the amount with a BS or P&L section for the "
                "Tax Entries (CTE) column in the combined views."
            )
        note = QLabel(note_txt)
        note.setWordWrap(True)
        note.setStyleSheet("font-size: 11px; color: #666;")

        btn_row = QHBoxLayout()
        lbl = "EJE" if self._workpaper == "elim" else "CTE"
        btn_add = QPushButton(f"+ Add {lbl}")
        btn_add.setStyleSheet(_BTN_NAVY)
        btn_add.clicked.connect(self._on_add)
        btn_del = QPushButton("Remove")
        btn_del.setStyleSheet(_BTN)
        btn_del.clicked.connect(self._on_remove)
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_del)
        btn_row.addStretch()

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Description", "Section / Line", "Amount"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setStyleSheet(_HDR_STYLE)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.itemChanged.connect(self._on_changed)

        layout.addWidget(note)
        layout.addLayout(btn_row)
        layout.addWidget(self._table)

    def refresh(self):
        self._table.blockSignals(True)
        self._table.setRowCount(0)
        with db_connection(self._path) as conn:
            rows = conn.execute(
                "SELECT wp_line_id, description, line_type, amount "
                "FROM workpaper_lines WHERE job_id = ? AND workpaper = ? "
                "ORDER BY sort_order",
                (self._job_id, self._workpaper),
            ).fetchall()
        for row in rows:
            r = self._table.rowCount()
            self._table.insertRow(r)
            desc_item = QTableWidgetItem(row["description"])
            desc_item.setData(Qt.UserRole, row["wp_line_id"])
            sec_item  = QTableWidgetItem(row["line_type"] or "")
            amt_item  = QTableWidgetItem(_fmt(float(row["amount"])))
            amt_item.setFont(QFont("Consolas"))
            amt_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._table.setItem(r, 0, desc_item)
            self._table.setItem(r, 1, sec_item)
            self._table.setItem(r, 2, amt_item)
        self._table.blockSignals(False)

    def _on_add(self):
        r = self._table.rowCount()
        self._table.insertRow(r)
        wid = new_uuid()
        with db_connection(self._path) as conn:
            default_desc = "New elimination" if self._workpaper == "elim" else "New tax entry"
            conn.execute(
                "INSERT INTO workpaper_lines "
                "(wp_line_id, job_id, workpaper, description, amount, "
                " line_type, sort_order, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (wid, self._job_id, self._workpaper, default_desc, 0.0, "", r, _now()),
            )
        desc_item = QTableWidgetItem(default_desc)
        desc_item.setData(Qt.UserRole, wid)
        self._table.setItem(r, 0, desc_item)
        self._table.setItem(r, 1, QTableWidgetItem(""))
        amt_item = QTableWidgetItem("—")
        amt_item.setFont(QFont("Consolas"))
        amt_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._table.setItem(r, 2, amt_item)
        self._table.editItem(self._table.item(r, 0))
        self.changed.emit()

    def _on_remove(self):
        rows = {i.row() for i in self._table.selectedItems()}
        if not rows:
            return
        ids = [self._table.item(r, 0).data(Qt.UserRole)
               for r in rows if self._table.item(r, 0)]
        with db_connection(self._path) as conn:
            for wid in ids:
                conn.execute("DELETE FROM workpaper_lines WHERE wp_line_id = ?", (wid,))
        self.refresh()
        self.changed.emit()

    def _on_changed(self, item: QTableWidgetItem):
        row = item.row()
        wid = self._table.item(row, 0).data(Qt.UserRole) if self._table.item(row, 0) else None
        if not wid:
            return
        col = item.column()
        try:
            with db_connection(self._path) as conn:
                if col == 0:
                    conn.execute(
                        "UPDATE workpaper_lines SET description = ? WHERE wp_line_id = ?",
                        (item.text(), wid),
                    )
                elif col == 1:
                    conn.execute(
                        "UPDATE workpaper_lines SET line_type = ? WHERE wp_line_id = ?",
                        (item.text(), wid),
                    )
                elif col == 2:
                    raw = item.text().replace(",", "").replace("(", "-").replace(")", "")
                    try:
                        amt = float(raw)
                    except ValueError:
                        return
                    conn.execute(
                        "UPDATE workpaper_lines SET amount = ? WHERE wp_line_id = ?",
                        (amt, wid),
                    )
        except Exception:
            pass
        else:
            self.changed.emit()


# ── Collapsible EJE panel (lives at the bottom of the combined view) ──────────

class _EntryTabPanel(QWidget):
    """
    Hosts the account-level EJE/CTE editors as a plain tab (alongside Combined
    Balance Sheet / P&L / Summary / Notes) instead of a permanently-docked
    panel — keeps the combined financials as the main view instead of
    competing with an always-visible entry editor for screen space.

    The legacy flat section-level editor is intentionally not shown here —
    it added a second stacked editor per tab and ate more space. Any entries
    created with it before this UI existed still open correctly and still
    count toward the combined totals (see _refresh_combined); they just
    aren't editable from this panel anymore.
    """

    changed = Signal()

    def __init__(self, path: Path, job_id: str, parent=None):
        super().__init__(parent)
        lo = QVBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(0)

        inner_tabs = QTabWidget()
        inner_tabs.setDocumentMode(True)
        inner_tabs.setStyleSheet(
            "QTabBar::tab { padding: 4px 14px; font-size: 11px; font-weight: bold; }"
            f"QTabBar::tab:selected {{ background: {_NAVY}; color: #FFF; }}"
        )

        self._eje_acct = _ConsolEntryEditor(path, job_id, workpaper="elim")
        self._cte_acct = _ConsolEntryEditor(path, job_id, workpaper="cte")
        self._eje_acct.changed.connect(self.changed.emit)
        self._cte_acct.changed.connect(self.changed.emit)

        inner_tabs.addTab(self._eje_acct, "EJE  —  Eliminating Entries")
        inner_tabs.addTab(self._cte_acct, "CTE  —  Tax Entries")
        lo.addWidget(inner_tabs)
        self._inner_tabs = inner_tabs

    def set_members(self, members: list[dict]):
        """Push the current subsidiary list into the account-level editors'
        account pickers. members: [{"member_id","label","file_path"}]."""
        self._eje_acct.set_members(members)
        self._cte_acct.set_members(members)

    def open_new_entry_for_account(self, workpaper: str, member_id: str, account_id: str):
        """Jump straight to a fresh EJE/CTE entry with the first line already
        pointed at this account — used by the combined statement preview's
        right-click 'Create Entry' menu."""
        editor = self._eje_acct if workpaper == "elim" else self._cte_acct
        self._inner_tabs.setCurrentWidget(editor)
        editor._on_new_entry()
        combo = editor._lines_table.cellWidget(0, _CE_COL_ACCT)
        if combo:
            combo.set_selection(member_id, account_id)
            combo.setFocus()
        editor._update_balance()

    def refresh(self):
        self._eje_acct.refresh()
        self._cte_acct.refresh()


# ── Package reader helpers ────────────────────────────────────────────────────
# Pure data-reading logic lives in models/consolidation_read.py (no Qt
# dependency) so the Excel exporter can share it instead of duplicating —
# these are thin aliases kept so the rest of this file doesn't need renaming.

_read_member_info          = consolidation_read.read_member_info
_read_member_financials    = consolidation_read.read_member_financials
_read_member_account_index = consolidation_read.read_member_account_index
_merge_into                 = consolidation_read.merge_into
