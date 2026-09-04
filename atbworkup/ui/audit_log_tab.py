"""
Audit Log tab — read-only view of the activity_log table.

Toolbar filters:
  Package Version  (All | 1 | 2 | …)
  Event Type       (All | imported_tb | added_aje | …)
  Free-text search (filters Description column)
  [Refresh]

Table columns: Date/Time | Event | Entity | Description | Performed By | Pkg Ver
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from atbworkup.db.connection import db_connection


_HDR_STYLE = (
    "QHeaderView::section { background: #1A2B4C; color: white; "
    "font-weight: bold; padding: 4px 8px; border: none; "
    "border-right: 1px solid #2A3B5C; }"
)
_BAR_STYLE = "background: #F7F7F7; border-bottom: 1px solid #E0E0E0; padding: 4px 8px;"
_BTN_STYLE = (
    "QPushButton { font-size: 11px; padding: 2px 10px; border: 1px solid #CCCCCC;"
    "border-radius: 3px; background: #FFFFFF; color: #333333; }"
    "QPushButton:hover { background: #E4EEFB; }"
)

# Human-readable labels for common event types
_EVENT_LABELS = {
    "imported_tb":   "Import TB",
    "added_aje":     "Add AJE",
    "changed_aje":   "Change AJE",
    "deleted_aje":   "Delete AJE",
    "mapped_account":"Map Account",
    "export_package":"Export Package",
    "created_job":   "Create Job",
    "updated_job":   "Update Job",
    "added_preparer_note":  "Add Note (Prep)",
    "added_reviewer_note":  "Add Note (Rev)",
    "added_client_note":    "Add Note (Client)",
}

_COL_HEADERS = ["Date / Time", "Event", "Entity", "Description", "Performed By", "Pkg Ver"]


class AuditLogTab(QWidget):
    def __init__(self, path: str | Path, job_id: str, parent=None):
        super().__init__(parent)
        self._path   = Path(path)
        self._job_id = job_id
        self._rows: list[dict] = []
        self._build_ui()
        self.refresh()

    # ── Build ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Filter bar
        bar = QWidget()
        bar.setStyleSheet(_BAR_STYLE)
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(8, 4, 8, 4)
        bar_layout.setSpacing(8)

        bar_layout.addWidget(QLabel("Package:"))
        self._pkg_filter = QComboBox()
        self._pkg_filter.setFixedWidth(70)
        self._pkg_filter.addItem("All", None)
        self._pkg_filter.currentIndexChanged.connect(self._apply_filter)
        bar_layout.addWidget(self._pkg_filter)

        bar_layout.addWidget(QLabel("Event:"))
        self._event_filter = QComboBox()
        self._event_filter.setFixedWidth(150)
        self._event_filter.addItem("All", None)
        self._event_filter.currentIndexChanged.connect(self._apply_filter)
        bar_layout.addWidget(self._event_filter)

        bar_layout.addWidget(QLabel("Search:"))
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter description…")
        self._search.setMaximumWidth(240)
        self._search.textChanged.connect(self._apply_filter)
        bar_layout.addWidget(self._search)

        bar_layout.addStretch()

        btn_refresh = QPushButton("Refresh")
        btn_refresh.setStyleSheet(_BTN_STYLE)
        btn_refresh.clicked.connect(self.refresh)
        bar_layout.addWidget(btn_refresh)

        root.addWidget(bar)

        # Table
        self._table = QTableWidget(0, len(_COL_HEADERS))
        self._table.setHorizontalHeaderLabels(_COL_HEADERS)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.horizontalHeader().setStyleSheet(_HDR_STYLE)

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.Stretch)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeToContents)

        root.addWidget(self._table, 1)

    # ── Data ──────────────────────────────────────────────────────────────

    def refresh(self):
        with db_connection(self._path) as conn:
            rows = conn.execute(
                """SELECT activity_id, event_type, entity_type, entity_id,
                          description, performed_by, performed_at, package_version
                   FROM activity_log
                   WHERE job_id = ?
                   ORDER BY performed_at DESC""",
                (self._job_id,),
            ).fetchall()
        self._rows = [dict(r) for r in rows]
        self._rebuild_filters()
        self._apply_filter()

    def _rebuild_filters(self):
        # Package versions
        versions = sorted({r["package_version"] for r in self._rows
                           if r["package_version"] is not None})
        self._pkg_filter.blockSignals(True)
        cur_pkg = self._pkg_filter.currentData()
        self._pkg_filter.clear()
        self._pkg_filter.addItem("All", None)
        for v in versions:
            self._pkg_filter.addItem(f"V{v:02d}", v)
        idx = self._pkg_filter.findData(cur_pkg)
        self._pkg_filter.setCurrentIndex(max(idx, 0))
        self._pkg_filter.blockSignals(False)

        # Event types
        events = sorted({r["event_type"] for r in self._rows})
        self._event_filter.blockSignals(True)
        cur_ev = self._event_filter.currentData()
        self._event_filter.clear()
        self._event_filter.addItem("All", None)
        for ev in events:
            self._event_filter.addItem(_EVENT_LABELS.get(ev, ev), ev)
        idx = self._event_filter.findData(cur_ev)
        self._event_filter.setCurrentIndex(max(idx, 0))
        self._event_filter.blockSignals(False)

    def _apply_filter(self, *_):
        pkg_filter   = self._pkg_filter.currentData()
        event_filter = self._event_filter.currentData()
        search_text  = self._search.text().strip().lower()

        filtered = [
            r for r in self._rows
            if (pkg_filter   is None or r["package_version"] == pkg_filter)
            and (event_filter is None or r["event_type"]      == event_filter)
            and (not search_text or search_text in (r["description"] or "").lower())
        ]
        self._populate_table(filtered)

    def _populate_table(self, rows: list[dict]):
        self._table.setRowCount(0)
        for r in rows:
            row_idx = self._table.rowCount()
            self._table.insertRow(row_idx)

            # Format ISO timestamp → local-friendly
            ts = r["performed_at"] or ""
            ts_display = ts.replace("T", "  ").replace("Z", "")

            pkg = r["package_version"]
            pkg_display = f"V{pkg:02d}" if pkg is not None else "—"
            event_label = _EVENT_LABELS.get(r["event_type"], r["event_type"])

            cells = [
                ts_display,
                event_label,
                r["entity_type"] or "—",
                r["description"] or "",
                r["performed_by"] or "—",
                pkg_display,
            ]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(str(text))
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                if col in (0, 1, 4, 5):
                    item.setTextAlignment(Qt.AlignCenter)
                self._table.setItem(row_idx, col, item)

            # Tint export-package rows lightly
            if r["event_type"] == "export_package":
                for col in range(len(_COL_HEADERS)):
                    it = self._table.item(row_idx, col)
                    if it:
                        it.setBackground(QColor("#EEF4FF"))
