"""
Workpapers tab — M-1, M-2, and K-1 for 1065, 1120-S, and 1120 binders.

M-1: Book-to-tax income reconciliation.
     Book income (AJE+RJE only) and tax income (all entries) are auto-computed.
     Users add manual explanation lines that should sum to the total difference.

M-2: Accumulated Adjustments Account (1120-S) / Partners' Capital (1065).
     Net income row is auto-pulled from the binder; other rows are manual.

K-1: Partner/shareholder roster with auto-allocated Schedule K items.
"""
from __future__ import annotations

import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QPushButton, QLabel, QFrame,
    QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QCheckBox,
    QSpinBox, QDoubleSpinBox, QMessageBox, QComboBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor

from atbworkup.db.connection import db_connection
from atbworkup.utils.ids import new_uuid

_NAVY      = "#1A2B4C"
_PY_FG     = "#5A6A8A"
_AMBER     = "#B85C00"
_GREEN     = "#2A6A4A"
_SECTION_BG = "#F2F4F6"

_HDR_STYLE = (
    f"QHeaderView::section {{ background: {_NAVY}; color: white; "
    "font-size: 12px; font-weight: bold; padding: 4px 8px; border: none; "
    "border-right: 1px solid #2A3B5C; }}"
)
_BTN = (
    "QPushButton { font-size: 11px; padding: 3px 12px; border: 1px solid #CCCCCC; "
    "border-radius: 3px; background: #FFFFFF; } "
    "QPushButton:hover { background: #E4EEFB; }"
)
_BTN_NAVY = (
    "QPushButton { font-size: 11px; padding: 3px 12px; border-radius: 3px; "
    f"background: {_NAVY}; color: #FFF; font-weight: bold; }} "
    f"QPushButton:hover {{ background: #2A3B6C; }}"
)


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fmt(v: float) -> str:
    if abs(v) < 0.005:
        return "—"
    return f"({abs(v):,.2f})" if v < 0 else f"{v:,.2f}"


def _bold_font() -> QFont:
    f = QFont()
    f.setBold(True)
    return f


def _mono_font(bold: bool = False) -> QFont:
    f = QFont("Consolas")
    f.setBold(bold)
    return f


class WorkpapersTab(QWidget):
    """M-1 / M-2 / K-1 workpapers for flow-through and corporate binders."""

    def __init__(self, path: str | Path, job_id: str, entity_type: str, parent=None):
        super().__init__(parent)
        self._path        = Path(path)
        self._job_id      = job_id
        self._entity_type = entity_type
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        root.addWidget(self._tabs)

        self._m1_widget = _M1Widget(self._path, self._job_id, self)
        self._tabs.addTab(self._m1_widget, "M-1 Reconciliation")

        et = self._entity_type
        if et in ("1065", "1120S"):
            label = "M-2  (Partners' Capital)" if et == "1065" else "M-2  (AAA)"
            self._m2_widget = _M2Widget(self._path, self._job_id, et, self)
            self._tabs.addTab(self._m2_widget, label)

            self._k1_widget = _K1Widget(self._path, self._job_id, self)
            self._tabs.addTab(self._k1_widget, "K-1 Allocations")

    def refresh(self):
        self._m1_widget.refresh()
        if hasattr(self, "_m2_widget"):
            self._m2_widget.refresh()
        if hasattr(self, "_k1_widget"):
            self._k1_widget.refresh()


# ── M-1 ───────────────────────────────────────────────────────────────────────

class _M1Widget(QWidget):
    """Book-to-tax income reconciliation."""

    def __init__(self, path: Path, job_id: str, parent=None):
        super().__init__(parent)
        self._path   = path
        self._job_id = job_id
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        # ── Auto-computed summary ────────────────────────────────────────
        summary_frame = QFrame()
        summary_frame.setStyleSheet(
            f"QFrame {{ background: {_SECTION_BG}; border: 1px solid #DDDDDD; "
            "border-radius: 4px; padding: 8px; }}"
        )
        sf_layout = QHBoxLayout(summary_frame)
        sf_layout.setContentsMargins(12, 8, 12, 8)
        sf_layout.setSpacing(32)

        self._lbl_book  = _SummaryLabel("Book Net Income", "—")
        self._lbl_tax   = _SummaryLabel("Tax Net Income", "—")
        self._lbl_diff  = _SummaryLabel("Book–Tax Difference", "—")

        sf_layout.addWidget(self._lbl_book)
        sf_layout.addWidget(_vline())
        sf_layout.addWidget(self._lbl_tax)
        sf_layout.addWidget(_vline())
        sf_layout.addWidget(self._lbl_diff)
        sf_layout.addStretch()

        note = QLabel(
            "Book income = AJE + RJE adjustments only.  "
            "Tax income = Book + FTJE adjustments.  "
            "Explanation lines below should account for the difference."
        )
        note.setStyleSheet("font-size: 11px; color: #666666;")
        note.setWordWrap(True)

        # ── Manual explanation lines ─────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_add = QPushButton("+ Add Line")
        btn_add.setStyleSheet(_BTN_NAVY)
        btn_add.clicked.connect(self._on_add)
        btn_del = QPushButton("Remove Selected")
        btn_del.setStyleSheet(_BTN)
        btn_del.clicked.connect(self._on_remove)
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_del)
        btn_row.addStretch()

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Description", "Amount", "Type"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setStyleSheet(_HDR_STYLE)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.itemChanged.connect(self._on_item_changed)

        layout.addWidget(summary_frame)
        layout.addWidget(note)
        layout.addLayout(btn_row)
        layout.addWidget(self._table)

    def refresh(self):
        summary = _compute_m1_summary(self._path, self._job_id)
        book    = summary["book_income"]
        tax     = summary["tax_income"]
        diff    = summary["difference"]

        self._lbl_book.set_value(_fmt(book))
        self._lbl_tax.set_value(_fmt(tax))
        self._lbl_diff.set_value(_fmt(diff))
        color = _GREEN if abs(diff) < 0.005 else _AMBER
        self._lbl_diff.set_color(color)

        self._load_lines()

    def _load_lines(self):
        self._table.blockSignals(True)
        self._table.setRowCount(0)
        with db_connection(self._path) as conn:
            rows = conn.execute(
                "SELECT wp_line_id, description, amount, line_type "
                "FROM workpaper_lines WHERE job_id = ? AND workpaper = 'm1' "
                "ORDER BY sort_order, created_at",
                (self._job_id,),
            ).fetchall()
        for row in rows:
            r = self._table.rowCount()
            self._table.insertRow(r)
            desc_item = QTableWidgetItem(row["description"])
            desc_item.setData(Qt.UserRole, row["wp_line_id"])
            amt_item = QTableWidgetItem(_fmt(float(row["amount"])))
            amt_item.setFont(_mono_font())
            amt_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            type_item = QTableWidgetItem(row["line_type"] or "")
            self._table.setItem(r, 0, desc_item)
            self._table.setItem(r, 1, amt_item)
            self._table.setItem(r, 2, type_item)
        self._table.blockSignals(False)

    def _on_add(self):
        dlg = _M1LineDialog(parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        desc, amount, ltype = dlg.values()
        with db_connection(self._path) as conn:
            conn.execute(
                "INSERT INTO workpaper_lines "
                "(wp_line_id, job_id, workpaper, description, amount, line_type, "
                " sort_order, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (new_uuid(), self._job_id, "m1", desc, amount, ltype,
                 self._table.rowCount(), _now()),
            )
        self._load_lines()

    def _on_remove(self):
        rows = {i.row() for i in self._table.selectedItems()}
        if not rows:
            return
        ids = [self._table.item(r, 0).data(Qt.UserRole) for r in rows
               if self._table.item(r, 0)]
        if not ids:
            return
        with db_connection(self._path) as conn:
            for wid in ids:
                conn.execute("DELETE FROM workpaper_lines WHERE wp_line_id = ?", (wid,))
        self._load_lines()

    def _on_item_changed(self, item: QTableWidgetItem):
        row = item.row()
        wp_id = self._table.item(row, 0).data(Qt.UserRole) if self._table.item(row, 0) else None
        if not wp_id:
            return
        col = item.column()
        try:
            with db_connection(self._path) as conn:
                if col == 0:
                    conn.execute(
                        "UPDATE workpaper_lines SET description = ? WHERE wp_line_id = ?",
                        (item.text(), wp_id),
                    )
                elif col == 1:
                    raw = item.text().replace(",", "").replace("(", "-").replace(")", "")
                    try:
                        amt = float(raw)
                    except ValueError:
                        return
                    conn.execute(
                        "UPDATE workpaper_lines SET amount = ? WHERE wp_line_id = ?",
                        (amt, wp_id),
                    )
                elif col == 2:
                    conn.execute(
                        "UPDATE workpaper_lines SET line_type = ? WHERE wp_line_id = ?",
                        (item.text(), wp_id),
                    )
        except Exception:
            pass


# ── M-2 ───────────────────────────────────────────────────────────────────────

class _M2Widget(QWidget):
    """AAA schedule (1120-S) or Partners' Capital Account Analysis (1065)."""

    # Fixed row definitions: (label, line_type, editable, auto_from_m1)
    _ROWS_1120S = [
        ("Beginning AAA Balance",             "begin_aaa",    True,  False),
        ("Ordinary Income / (Loss)",          "net_income",   False, True),
        ("Other Additions",                   "other_add",    True,  False),
        ("Other Reductions",                  "other_red",    True,  False),
        ("Non-Deductible Expenses",           "nondeduc",     True,  False),
        ("Distributions",                     "distrib",      True,  False),
    ]
    _ROWS_1065 = [
        ("Beginning Capital Balance",         "begin_cap",    True,  False),
        ("Capital Contributed During Year",   "contrib",      True,  False),
        ("Net Income / (Loss)",               "net_income",   False, True),
        ("Other Increases",                   "other_add",    True,  False),
        ("Distributions",                     "distrib",      True,  False),
        ("Other Decreases",                   "other_red",    True,  False),
    ]

    def __init__(self, path: Path, job_id: str, entity_type: str, parent=None):
        super().__init__(parent)
        self._path        = path
        self._job_id      = job_id
        self._entity_type = entity_type
        self._row_defs    = self._ROWS_1065 if entity_type == "1065" else self._ROWS_1120S
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        note = QLabel(
            "Auto rows (grey) are computed from journal entries.  "
            "Double-click any editable cell to update the amount."
        )
        note.setStyleSheet("font-size: 11px; color: #666666;")

        self._table = QTableWidget(len(self._row_defs) + 1, 2)
        self._table.setHorizontalHeaderLabels(["Item", "Amount"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setStyleSheet(_HDR_STYLE)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(False)
        self._table.itemChanged.connect(self._on_item_changed)

        layout.addWidget(note)
        layout.addWidget(self._table)

    def refresh(self):
        summary = _compute_m1_summary(self._path, self._job_id)
        net_income = summary["tax_income"]

        # Load manual overrides
        with db_connection(self._path) as conn:
            saved = {
                row["line_type"]: float(row["amount"])
                for row in conn.execute(
                    "SELECT line_type, amount FROM workpaper_lines "
                    "WHERE job_id = ? AND workpaper = 'm2'",
                    (self._job_id,),
                ).fetchall()
            }

        self._table.blockSignals(True)
        running = 0.0
        for r, (label, ltype, editable, auto) in enumerate(self._row_defs):
            amount = net_income if auto else saved.get(ltype, 0.0)
            running += amount

            lbl_item = QTableWidgetItem(label)
            lbl_item.setFlags(Qt.ItemIsEnabled)
            lbl_item.setData(Qt.UserRole, ltype)
            if auto:
                lbl_item.setForeground(QColor(_PY_FG))

            amt_item = QTableWidgetItem(_fmt(amount))
            amt_item.setFont(_mono_font())
            amt_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if not editable:
                amt_item.setFlags(Qt.ItemIsEnabled)
                amt_item.setForeground(QColor(_PY_FG))

            self._table.setItem(r, 0, lbl_item)
            self._table.setItem(r, 1, amt_item)

        # Ending balance row
        end_row = len(self._row_defs)
        end_label = "Ending Balance"
        end_lbl = QTableWidgetItem(end_label)
        end_lbl.setFlags(Qt.ItemIsEnabled)
        end_lbl.setFont(_bold_font())
        end_amt = QTableWidgetItem(_fmt(running))
        end_amt.setFlags(Qt.ItemIsEnabled)
        end_amt.setFont(_mono_font(bold=True))
        end_amt.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._table.setItem(end_row, 0, end_lbl)
        self._table.setItem(end_row, 1, end_amt)

        self._table.blockSignals(False)

    def _on_item_changed(self, item: QTableWidgetItem):
        row = item.row()
        if row >= len(self._row_defs):
            return
        _, ltype, editable, auto = self._row_defs[row]
        if not editable or auto:
            return
        if item.column() != 1:
            return
        raw = item.text().replace(",", "").replace("(", "-").replace(")", "")
        try:
            amt = float(raw)
        except ValueError:
            return
        with db_connection(self._path) as conn:
            existing = conn.execute(
                "SELECT wp_line_id FROM workpaper_lines "
                "WHERE job_id = ? AND workpaper = 'm2' AND line_type = ?",
                (self._job_id, ltype),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE workpaper_lines SET amount = ? WHERE wp_line_id = ?",
                    (amt, existing["wp_line_id"]),
                )
            else:
                conn.execute(
                    "INSERT INTO workpaper_lines "
                    "(wp_line_id, job_id, workpaper, description, amount, line_type, "
                    " sort_order, created_at) VALUES (?,?,?,?,?,?,?,?)",
                    (new_uuid(), self._job_id, "m2", ltype, amt, ltype,
                     row, _now()),
                )
        # Recompute ending balance without full refresh to avoid signal loop
        self._table.blockSignals(True)
        total = 0.0
        for r2, (_, lt2, _, auto2) in enumerate(self._row_defs):
            cell = self._table.item(r2, 1)
            if cell:
                raw2 = cell.text().replace(",", "").replace("(", "-").replace(")", "").replace("—", "0")
                try:
                    total += float(raw2)
                except ValueError:
                    pass
        end_cell = self._table.item(len(self._row_defs), 1)
        if end_cell:
            end_cell.setText(_fmt(total))
        self._table.blockSignals(False)


# ── K-1 ───────────────────────────────────────────────────────────────────────

class _K1Widget(QWidget):
    """Partner/shareholder roster and K-1 item allocation."""

    def __init__(self, path: Path, job_id: str, parent=None):
        super().__init__(parent)
        self._path   = path
        self._job_id = job_id
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # ── Roster ──────────────────────────────────────────────────────
        roster_label = QLabel("Partner / Shareholder Roster")
        roster_label.setFont(_bold_font())

        roster_btns = QHBoxLayout()
        btn_add = QPushButton("+ Add Owner")
        btn_add.setStyleSheet(_BTN_NAVY)
        btn_add.clicked.connect(self._on_add_owner)
        btn_del = QPushButton("Remove Selected")
        btn_del.setStyleSheet(_BTN)
        btn_del.clicked.connect(self._on_remove_owner)
        self._lbl_pct = QLabel("Total: 0.00%")
        self._lbl_pct.setStyleSheet("font-size: 11px; color: #666;")
        roster_btns.addWidget(btn_add)
        roster_btns.addWidget(btn_del)
        roster_btns.addStretch()
        roster_btns.addWidget(self._lbl_pct)

        self._roster = QTableWidget(0, 3)
        self._roster.setHorizontalHeaderLabels(["Name", "TIN", "Ownership %"])
        self._roster.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._roster.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._roster.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._roster.horizontalHeader().setStyleSheet(_HDR_STYLE)
        self._roster.verticalHeader().setVisible(False)
        self._roster.setMaximumHeight(180)
        self._roster.setAlternatingRowColors(True)
        self._roster.itemChanged.connect(self._on_roster_changed)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #DDDDDD;")

        # ── Allocation table ─────────────────────────────────────────────
        alloc_label = QLabel("K-1 Item Allocations  (auto-computed from Schedule K mappings)")
        alloc_label.setFont(_bold_font())

        btn_refresh = QPushButton("Recalculate")
        btn_refresh.setStyleSheet(_BTN)
        btn_refresh.clicked.connect(self.refresh)

        alloc_top = QHBoxLayout()
        alloc_top.addWidget(alloc_label)
        alloc_top.addStretch()
        alloc_top.addWidget(btn_refresh)

        self._alloc = QTableWidget(0, 2)  # columns built dynamically
        self._alloc.horizontalHeader().setStyleSheet(_HDR_STYLE)
        self._alloc.verticalHeader().setVisible(False)
        self._alloc.setAlternatingRowColors(True)
        self._alloc.setEditTriggers(QTableWidget.NoEditTriggers)

        layout.addWidget(roster_label)
        layout.addLayout(roster_btns)
        layout.addWidget(self._roster)
        layout.addWidget(sep)
        layout.addLayout(alloc_top)
        layout.addWidget(self._alloc)

    def refresh(self):
        self._load_roster()
        self._build_allocation()

    def _load_roster(self):
        self._roster.blockSignals(True)
        self._roster.setRowCount(0)
        with db_connection(self._path) as conn:
            rows = conn.execute(
                "SELECT owner_id, name, tin, ownership_pct FROM owners "
                "WHERE job_id = ? ORDER BY sort_order, created_at",
                (self._job_id,),
            ).fetchall()
        total = 0.0
        for row in rows:
            r = self._roster.rowCount()
            self._roster.insertRow(r)
            name_item = QTableWidgetItem(row["name"])
            name_item.setData(Qt.UserRole, row["owner_id"])
            tin_item  = QTableWidgetItem(row["tin"] or "")
            pct_item  = QTableWidgetItem(f"{row['ownership_pct']:.4f}")
            pct_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._roster.setItem(r, 0, name_item)
            self._roster.setItem(r, 1, tin_item)
            self._roster.setItem(r, 2, pct_item)
            total += float(row["ownership_pct"])
        color = _GREEN if abs(total - 100.0) < 0.005 else _AMBER
        self._lbl_pct.setText(f"Total: {total:.4f}%")
        self._lbl_pct.setStyleSheet(f"font-size: 11px; color: {color}; font-weight: bold;")
        self._roster.blockSignals(False)

    def _build_allocation(self):
        # NOTE: Schedule K tax lines are seeded with financial_statement =
        # 'ProfitAndLoss' (section = "Schedule K — Pass-Through"), never the
        # literal string 'ScheduleK' — filtering on that never matched any
        # real tax line, so this table always showed "no accounts mapped"
        # even when K-1 accounts existed. category = 'schedule_k' is the
        # correct, stored signal (see atbworkup/data/tax_line_categories.py).
        from atbworkup.data.tax_line_categories import CATEGORY_SCHEDULE_K
        with db_connection(self._path) as conn:
            k_rows = conn.execute(
                """
                SELECT tl.line_code, tl.line_name,
                       COALESCE(SUM(
                           CASE WHEN je.status != 'Void' OR je.aje_id IS NULL
                                THEN COALESCE(jel.amount, 0) ELSE 0 END
                       ) + COALESCE(a.pbc_balance, 0), 0) AS total_raw,
                       a.normal_balance
                FROM accounts a
                JOIN mappings m ON m.account_id = a.account_id AND m.job_id = a.job_id
                JOIN tax_lines tl ON tl.tax_line_id = m.tax_line_id
                    AND tl.category = ?
                LEFT JOIN journal_entry_lines jel ON jel.account_id = a.account_id
                LEFT JOIN journal_entries je
                    ON je.aje_id = jel.aje_id AND je.job_id = a.job_id
                WHERE a.job_id = ?
                GROUP BY tl.tax_line_id
                ORDER BY tl.section_sort_order, tl.sort_order
                """,
                (CATEGORY_SCHEDULE_K, self._job_id),
            ).fetchall()

            owners = conn.execute(
                "SELECT owner_id, name, ownership_pct FROM owners "
                "WHERE job_id = ? ORDER BY sort_order, created_at",
                (self._job_id,),
            ).fetchall()

        if not k_rows:
            self._alloc.setColumnCount(2)
            self._alloc.setHorizontalHeaderLabels(["K Item", "Total"])
            self._alloc.setRowCount(1)
            msg = QTableWidgetItem("No accounts mapped to Schedule K lines yet.")
            msg.setFlags(Qt.ItemIsEnabled)
            msg.setForeground(QColor("#888"))
            self._alloc.setItem(0, 0, msg)
            self._alloc.setItem(0, 1, QTableWidgetItem(""))
            return

        # Build columns: K Item | Total | Owner1 | Owner2 …
        ncols = 2 + len(owners)
        self._alloc.setColumnCount(ncols)
        headers = ["K Item", "Total"] + [o["name"] for o in owners]
        self._alloc.setHorizontalHeaderLabels(headers)
        hdr = self._alloc.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        for c in range(2, ncols):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)

        self._alloc.setRowCount(len(k_rows))
        for r, row in enumerate(k_rows):
            # Display amount: sign-flip for Credit-normal K items
            raw = float(row["total_raw"])
            display = -raw if row["normal_balance"] == "Credit" else raw

            lbl_item = QTableWidgetItem(f"{row['line_code']}  {row['line_name']}")
            lbl_item.setFlags(Qt.ItemIsEnabled)
            tot_item = QTableWidgetItem(_fmt(display))
            tot_item.setFont(QFont("Consolas"))
            tot_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            tot_item.setFlags(Qt.ItemIsEnabled)
            self._alloc.setItem(r, 0, lbl_item)
            self._alloc.setItem(r, 1, tot_item)

            for c, owner in enumerate(owners):
                alloc = display * (float(owner["ownership_pct"]) / 100.0)
                a_item = QTableWidgetItem(_fmt(alloc))
                a_item.setFont(QFont("Consolas"))
                a_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                a_item.setFlags(Qt.ItemIsEnabled)
                self._alloc.setItem(r, 2 + c, a_item)

    def _on_add_owner(self):
        dlg = _OwnerDialog(parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        name, tin, pct = dlg.values()
        with db_connection(self._path) as conn:
            conn.execute(
                "INSERT INTO owners "
                "(owner_id, job_id, name, tin, ownership_pct, sort_order, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (new_uuid(), self._job_id, name, tin or None, pct,
                 self._roster.rowCount(), _now()),
            )
        self.refresh()

    def _on_remove_owner(self):
        rows = {i.row() for i in self._roster.selectedItems()}
        if not rows:
            return
        ids = [self._roster.item(r, 0).data(Qt.UserRole) for r in rows
               if self._roster.item(r, 0)]
        with db_connection(self._path) as conn:
            for oid in ids:
                conn.execute("DELETE FROM owners WHERE owner_id = ?", (oid,))
        self.refresh()

    def _on_roster_changed(self, item: QTableWidgetItem):
        row  = item.row()
        col  = item.column()
        oid  = self._roster.item(row, 0).data(Qt.UserRole) if self._roster.item(row, 0) else None
        if not oid:
            return
        try:
            with db_connection(self._path) as conn:
                if col == 0:
                    conn.execute("UPDATE owners SET name = ? WHERE owner_id = ?",
                                 (item.text(), oid))
                elif col == 1:
                    conn.execute("UPDATE owners SET tin = ? WHERE owner_id = ?",
                                 (item.text() or None, oid))
                elif col == 2:
                    pct = float(item.text())
                    conn.execute("UPDATE owners SET ownership_pct = ? WHERE owner_id = ?",
                                 (pct, oid))
        except (ValueError, Exception):
            pass
        # Refresh pct total label
        self._load_roster()


# ── Helper widgets ─────────────────────────────────────────────────────────────

class _SummaryLabel(QWidget):
    def __init__(self, title: str, value: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self._title = QLabel(title)
        self._title.setStyleSheet("font-size: 11px; color: #666666;")
        self._value = QLabel(value)
        self._value.setFont(_mono_font(bold=True))
        self._value.setStyleSheet("font-size: 14px;")
        layout.addWidget(self._title)
        layout.addWidget(self._value)

    def set_value(self, v: str):
        self._value.setText(v)

    def set_color(self, color: str):
        self._value.setStyleSheet(f"font-size: 14px; color: {color};")


def _vline() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.VLine)
    f.setStyleSheet("color: #CCCCCC;")
    return f


# ── Dialogs ───────────────────────────────────────────────────────────────────

class _M1LineDialog(QDialog):
    _TYPES = ["Permanent", "Timing", "Other"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add M-1 Adjustment Line")
        self.setMinimumWidth(380)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._desc = QLineEdit()
        self._desc.setPlaceholderText("e.g. Meals & Entertainment (50%)")
        self._amt = QLineEdit("0.00")
        self._type = QComboBox()
        self._type.addItems(self._TYPES)
        form.addRow("Description:", self._desc)
        form.addRow("Amount:", self._amt)
        form.addRow("Type:", self._type)
        layout.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._validate)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _validate(self):
        if not self._desc.text().strip():
            QMessageBox.warning(self, "Required", "Description is required.")
            return
        try:
            float(self._amt.text())
        except ValueError:
            QMessageBox.warning(self, "Invalid", "Amount must be a number.")
            return
        self.accept()

    def values(self) -> tuple[str, float, str]:
        return (
            self._desc.text().strip(),
            float(self._amt.text()),
            self._type.currentText(),
        )


class _OwnerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Partner / Shareholder")
        self.setMinimumWidth(340)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._name = QLineEdit()
        self._tin  = QLineEdit()
        self._tin.setPlaceholderText("XX-XXXXXXX or XXX-XX-XXXX")
        self._pct  = QLineEdit("0.0000")
        form.addRow("Name *:",      self._name)
        form.addRow("TIN (opt.):",  self._tin)
        form.addRow("Ownership %:", self._pct)
        layout.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._validate)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _validate(self):
        if not self._name.text().strip():
            QMessageBox.warning(self, "Required", "Name is required.")
            return
        try:
            float(self._pct.text())
        except ValueError:
            QMessageBox.warning(self, "Invalid", "Ownership % must be a number.")
            return
        self.accept()

    def values(self) -> tuple[str, str, float]:
        return (
            self._name.text().strip(),
            self._tin.text().strip(),
            float(self._pct.text()),
        )


# ── Data helpers ───────────────────────────────────────────────────────────────

def _compute_m1_summary(path: Path, job_id: str) -> dict:
    """
    Compute book and tax net income from the binder.
    Book income = -(pbc + AJE + RJE) for P&L accounts.
    Tax income  = -(pbc + AJE + RJE + FTJE) for P&L accounts.
    """
    with db_connection(path) as conn:
        rows = conn.execute(
            """
            SELECT
                a.normal_balance,
                COALESCE(a.pbc_balance, 0) AS pbc,
                COALESCE(SUM(CASE WHEN je.entry_type IN ('AJE','RJE')
                                       AND je.status != 'Void'
                               THEN jel.amount ELSE 0 END), 0) AS book_adj,
                COALESCE(SUM(CASE WHEN je.entry_type = 'FTJE'
                                       AND je.status != 'Void'
                               THEN jel.amount ELSE 0 END), 0) AS ftje
            FROM accounts a
            JOIN mappings m
                ON m.account_id = a.account_id AND m.job_id = a.job_id
            JOIN tax_lines tl
                ON tl.tax_line_id = m.tax_line_id
                AND tl.financial_statement = 'ProfitAndLoss'
            LEFT JOIN journal_entry_lines jel ON jel.account_id = a.account_id
            LEFT JOIN journal_entries je
                ON je.aje_id = jel.aje_id AND je.job_id = a.job_id
            WHERE a.job_id = ?
            GROUP BY a.account_id
            """,
            (job_id,),
        ).fetchall()

    book_raw = 0.0
    tax_raw  = 0.0
    for r in rows:
        book_bal = float(r["pbc"]) + float(r["book_adj"])
        tax_bal  = book_bal + float(r["ftje"])
        book_raw += book_bal
        tax_raw  += tax_bal

    book_income = -book_raw
    tax_income  = -tax_raw
    return {
        "book_income": book_income,
        "tax_income":  tax_income,
        "difference":  book_income - tax_income,
    }
