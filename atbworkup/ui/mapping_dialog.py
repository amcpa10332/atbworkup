"""
Map selected accounts to a tax line.

Shows two grouped lists (Balance Sheet / Profit & Loss) with a search filter.
Supports single and bulk mapping.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTreeWidget, QTreeWidgetItem, QDialogButtonBox,
    QFrame,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush, QFont

from atbworkup.db.connection import db_connection
from atbworkup.db.settings import settings_connection, ensure_settings_db
from atbworkup.models.mappings import get_tax_line_templates, upsert_tax_line, map_accounts
from atbworkup.models.activity import log_activity
from atbworkup.ui.theme import RICH_NAVY, WHITE, PLATINUM, JET_BLACK


_FS_LABELS = {
    "BalanceSheet":  "Balance Sheet",
    "ProfitAndLoss": "Profit & Loss",
}
_FS_ORDER = ["BalanceSheet", "ProfitAndLoss"]


class MappingDialog(QDialog):
    """
    Shows all tax lines for the binder's entity type.
    User picks one line and clicks Map.
    """

    def __init__(self, path: str | Path, job_id: str, entity_type: str,
                 account_ids: list[str], account_names: list[str],
                 performed_by: str, parent=None):
        super().__init__(parent)
        self._path = Path(path)
        self._job_id = job_id
        self._entity_type = entity_type
        self._account_ids = account_ids
        self._account_names = account_names
        self._performed_by = performed_by
        self._templates: list[dict] = []

        self.setWindowTitle("Map to Tax Line")
        self.setMinimumSize(480, 520)
        self._build_ui()
        self._load_templates()

    # ── Build ────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # selected accounts summary
        count = len(self._account_ids)
        summary = ", ".join(self._account_names[:3])
        if count > 3:
            summary += f" … +{count - 3} more"
        lbl = QLabel(f"Mapping {count} account{'s' if count != 1 else ''}: {summary}")
        lbl.setWordWrap(True)
        lbl.setStyleSheet("font-weight: bold; color: #1A2B4C;")
        layout.addWidget(lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #E5E5E5;")
        layout.addWidget(sep)

        # search
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Search:"))
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter tax lines…")
        self._search.textChanged.connect(self._apply_filter)
        search_row.addWidget(self._search)
        layout.addLayout(search_row)

        # tax line tree
        self._tree = QTreeWidget()
        self._tree.setColumnCount(1)
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setSelectionMode(QTreeWidget.SingleSelection)
        self._tree.setStyleSheet("""
            QTreeWidget {
                font-family: "Segoe UI";
                font-size: 13px;
                background: #FFFFFF;
                color: #000000;
                border: 1px solid #E5E5E5;
            }
            QTreeWidget::item { padding: 4px 6px; }
            QTreeWidget::item:selected {
                background: #1A2B4C;
                color: #FFFFFF;
            }
            QTreeWidget::item:hover:!selected { background: #D0D8E8; }
        """)
        self._tree.itemSelectionChanged.connect(self._on_selection_changed)
        self._tree.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self._tree)

        # buttons
        btn_box = QDialogButtonBox()
        self._map_btn = QPushButton("Map")
        self._map_btn.setEnabled(False)
        self._map_btn.setDefault(True)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(
            "background: #E5E5E5; color: #000000; font-weight: normal;"
        )
        btn_box.addButton(self._map_btn, QDialogButtonBox.AcceptRole)
        btn_box.addButton(cancel_btn, QDialogButtonBox.RejectRole)
        btn_box.accepted.connect(self._do_map)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    # ── Data ─────────────────────────────────────────────────────────────

    def _load_templates(self):
        ensure_settings_db()
        with settings_connection() as sconn:
            self._templates = get_tax_line_templates(sconn, self._entity_type)
        self._populate_tree(self._templates)

    def _populate_tree(self, templates: list[dict]):
        self._tree.clear()
        groups: dict[str, list[dict]] = {}
        for t in templates:
            groups.setdefault(t["financial_statement"], []).append(t)

        header_font = QFont("Segoe UI", 11)
        header_font.setBold(True)

        for fs in _FS_ORDER:
            lines = groups.get(fs)
            if not lines:
                continue
            group_item = QTreeWidgetItem([_FS_LABELS.get(fs, fs)])
            group_item.setFlags(group_item.flags() & ~Qt.ItemIsSelectable)
            group_item.setFont(0, header_font)
            group_item.setBackground(0, QBrush(RICH_NAVY))
            group_item.setForeground(0, QBrush(WHITE))
            self._tree.addTopLevelItem(group_item)

            for line in lines:
                child = QTreeWidgetItem([line["line_name"]])
                child.setData(0, Qt.UserRole, line)
                group_item.addChild(child)

            group_item.setExpanded(True)

    def _apply_filter(self, text: str):
        text = text.strip().lower()
        filtered = [
            t for t in self._templates
            if not text or text in t["line_name"].lower()
        ]
        self._populate_tree(filtered)

    # ── Interaction ───────────────────────────────────────────────────────

    def _on_selection_changed(self):
        selected = self._tree.selectedItems()
        enabled = bool(selected and selected[0].data(0, Qt.UserRole))
        self._map_btn.setEnabled(enabled)

    def _on_double_click(self, item: QTreeWidgetItem, _col: int):
        if item.data(0, Qt.UserRole):
            self._do_map()

    def selected_template(self) -> dict | None:
        items = self._tree.selectedItems()
        if not items:
            return None
        return items[0].data(0, Qt.UserRole)

    def _do_map(self):
        template = self.selected_template()
        if not template:
            return

        with db_connection(self._path) as conn:
            tax_line_id = upsert_tax_line(
                conn,
                entity_type=self._entity_type,
                financial_statement=template["financial_statement"],
                section=template.get("section", ""),
                section_sort_order=template.get("section_sort_order", 0),
                line_code=template["line_code"],
                line_name=template["line_name"],
                sort_order=template["sort_order"],
                category=template.get("category", ""),
            )
            map_accounts(
                conn,
                job_id=self._job_id,
                account_ids=self._account_ids,
                tax_line_id=tax_line_id,
                mapped_by=self._performed_by,
            )
            log_activity(
                conn,
                job_id=self._job_id,
                event_type="changed_mapping",
                description=(
                    f"Mapped {len(self._account_ids)} account(s) to "
                    f"{template['line_name']} ({template['financial_statement']})"
                ),
                performed_by=self._performed_by,
            )

        self.accept()
