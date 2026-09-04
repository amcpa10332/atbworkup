"""
Mapping workbench — two-panel dialog for bulk account mapping.

Left:  unmapped accounts (multi-select)
Right: tax lines grouped by Balance Sheet / Profit & Loss

Select accounts on the left, click a tax line on the right to map them.
Mapped accounts disappear from the left list immediately.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTreeWidget, QTreeWidgetItem, QSplitter,
    QFrame, QWidget, QMenu, QMessageBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush, QFont

from atbworkup.db.connection import db_connection
from atbworkup.db.settings import settings_connection, ensure_settings_db
from atbworkup.models.mappings import get_tax_line_templates, upsert_tax_line, map_accounts
from atbworkup.models.accounts import delete_accounts
from atbworkup.models.activity import log_activity
from atbworkup.ui.theme import RICH_NAVY, WHITE, PLATINUM, JET_BLACK, TEXT_MUTED


_FS_LABELS = {"BalanceSheet": "Balance Sheet", "ProfitAndLoss": "Profit & Loss"}
_FS_ORDER  = ["BalanceSheet", "ProfitAndLoss"]

_ACCOUNT_COL_NUM  = 0
_ACCOUNT_COL_NAME = 1


class MappingWorkbench(QDialog):
    """
    Full-screen mapping utility.
    Left panel: unmapped accounts.
    Right panel: tax lines for this entity type.
    """

    def __init__(self, path: str | Path, job_id: str, entity_type: str,
                 performed_by: str, parent=None):
        super().__init__(parent)
        self._path        = Path(path)
        self._job_id      = job_id
        self._entity_type = entity_type
        self._performed_by = performed_by
        self._templates: list[dict] = []

        self.setWindowTitle("Map Accounts to Tax Lines")
        self.setMinimumSize(900, 580)
        self._build_ui()
        self._load_data()

    # ── Build ────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)

        # instruction bar
        tip = QLabel(
            "Select one or more accounts on the left, then click a tax line on the right to map them."
        )
        tip.setStyleSheet("color: #1A2B4C; font-style: italic; padding: 2px 0;")
        root.addWidget(tip)

        # splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(6)

        # ── Left: unmapped accounts ──────────────────────────────────────
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 4, 0)
        left_layout.setSpacing(4)

        left_header = QLabel("Unmapped Accounts")
        left_header.setStyleSheet(
            "background: #1A2B4C; color: #FFFFFF; font-weight: bold; "
            "letter-spacing: 1px; padding: 6px 8px;"
        )
        left_layout.addWidget(left_header)

        self._acct_search = QLineEdit()
        self._acct_search.setPlaceholderText("Filter accounts…")
        self._acct_search.textChanged.connect(self._filter_accounts)
        left_layout.addWidget(self._acct_search)

        self._acct_tree = QTreeWidget()
        self._acct_tree.setColumnCount(2)
        self._acct_tree.setHeaderLabels(["Acct #", "Account Name"])
        self._acct_tree.setRootIsDecorated(False)
        self._acct_tree.setSelectionMode(QTreeWidget.ExtendedSelection)
        self._acct_tree.setAlternatingRowColors(True)
        self._acct_tree.setStyleSheet(_list_style())
        self._acct_tree.header().setStretchLastSection(True)
        self._acct_tree.setColumnWidth(_ACCOUNT_COL_NUM, 90)
        self._acct_tree.itemSelectionChanged.connect(self._on_acct_selection)
        self._acct_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self._acct_tree.customContextMenuRequested.connect(self._on_acct_context_menu)
        left_layout.addWidget(self._acct_tree)

        self._acct_count_lbl = QLabel("")
        self._acct_count_lbl.setStyleSheet("color: #888888; font-size: 11px; padding: 2px 0;")
        left_layout.addWidget(self._acct_count_lbl)

        splitter.addWidget(left)

        # ── Right: tax lines ─────────────────────────────────────────────
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 0, 0, 0)
        right_layout.setSpacing(4)

        right_header = QLabel("Tax Lines")
        right_header.setStyleSheet(
            "background: #1A2B4C; color: #FFFFFF; font-weight: bold; "
            "letter-spacing: 1px; padding: 6px 8px;"
        )
        right_layout.addWidget(right_header)

        self._line_search = QLineEdit()
        self._line_search.setPlaceholderText("Filter tax lines…")
        self._line_search.textChanged.connect(self._filter_lines)
        right_layout.addWidget(self._line_search)

        self._line_tree = QTreeWidget()
        self._line_tree.setColumnCount(1)
        self._line_tree.setHeaderHidden(True)
        self._line_tree.setRootIsDecorated(True)
        self._line_tree.setStyleSheet(_list_style(clickable=True))
        self._line_tree.itemClicked.connect(self._on_line_clicked)
        right_layout.addWidget(self._line_tree)

        self._map_hint = QLabel("← Select accounts, then click a tax line to map")
        self._map_hint.setStyleSheet("color: #888888; font-style: italic; font-size: 11px; padding: 2px 0;")
        right_layout.addWidget(self._map_hint)

        splitter.addWidget(right)
        splitter.setSizes([420, 420])
        root.addWidget(splitter, 1)

        # ── Bottom bar ───────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #E5E5E5;")
        root.addWidget(sep)

        btn_row = QHBoxLayout()
        self._mapped_lbl = QLabel("")
        self._mapped_lbl.setStyleSheet("color: #2e7d32; font-weight: bold;")
        btn_row.addWidget(self._mapped_lbl)
        btn_row.addStretch()

        self._del_btn = QPushButton("Delete Selected…")
        self._del_btn.setEnabled(False)
        self._del_btn.setStyleSheet(
            "QPushButton { color: #7B1A1A; border: 1px solid #7B1A1A; "
            "background: #FFF; padding: 3px 10px; border-radius: 3px; }"
            "QPushButton:hover { background: #FDEAEA; }"
            "QPushButton:disabled { color: #AAAAAA; border-color: #CCCCCC; }"
        )
        self._del_btn.clicked.connect(self._on_delete_selected)
        btn_row.addWidget(self._del_btn)

        done_btn = QPushButton("Done")
        done_btn.setFixedWidth(90)
        done_btn.clicked.connect(self.accept)
        btn_row.addWidget(done_btn)
        root.addLayout(btn_row)

        self._mapped_count = 0

    # ── Data ─────────────────────────────────────────────────────────────

    def _load_data(self):
        ensure_settings_db()
        with settings_connection() as sconn:
            self._templates = get_tax_line_templates(sconn, self._entity_type)

        self._load_accounts()
        self._populate_lines(self._templates)

    def _load_accounts(self):
        with db_connection(self._path) as conn:
            rows = conn.execute(
                """SELECT account_id, account_number, account_name
                   FROM accounts
                   WHERE job_id = ? AND is_mapped = 0
                   ORDER BY account_number, account_name""",
                (self._job_id,),
            ).fetchall()
        self._all_accounts = [dict(r) for r in rows]
        self._populate_accounts(self._all_accounts)

    def _populate_accounts(self, accounts: list[dict]):
        self._acct_tree.clear()
        for a in accounts:
            item = QTreeWidgetItem([
                a.get("account_number") or "",
                a["account_name"],
            ])
            item.setData(0, Qt.UserRole, a["account_id"])
            self._acct_tree.addTopLevelItem(item)
        self._update_acct_count()

    def _populate_lines(self, templates: list[dict]):
        self._line_tree.clear()
        groups: dict[str, list[dict]] = {}
        for t in templates:
            groups.setdefault(t["financial_statement"], []).append(t)

        hdr_font = QFont("Segoe UI", 11)
        hdr_font.setBold(True)

        for fs in _FS_ORDER:
            lines = groups.get(fs)
            if not lines:
                continue
            group_item = QTreeWidgetItem([_FS_LABELS.get(fs, fs)])
            group_item.setFlags(group_item.flags() & ~Qt.ItemIsSelectable)
            group_item.setFont(0, hdr_font)
            group_item.setBackground(0, QBrush(RICH_NAVY))
            group_item.setForeground(0, QBrush(WHITE))
            self._line_tree.addTopLevelItem(group_item)
            for line in lines:
                child = QTreeWidgetItem([f"  {line['line_name']}"])
                child.setData(0, Qt.UserRole, line)
                group_item.addChild(child)
            group_item.setExpanded(True)

    def _update_acct_count(self):
        n = self._acct_tree.topLevelItemCount()
        self._acct_count_lbl.setText(f"{n} account{'s' if n != 1 else ''} remaining")

    # ── Interaction ───────────────────────────────────────────────────────

    def _filter_accounts(self, text: str):
        text = text.strip().lower()
        filtered = [
            a for a in self._all_accounts
            if not text
            or text in a["account_name"].lower()
            or text in (a.get("account_number") or "").lower()
        ]
        self._populate_accounts(filtered)

    def _filter_lines(self, text: str):
        text = text.strip().lower()
        filtered = [
            t for t in self._templates
            if not text or text in t["line_name"].lower()
        ]
        self._populate_lines(filtered)

    def _on_acct_selection(self):
        n = len(self._acct_tree.selectedItems())
        self._del_btn.setEnabled(n > 0)
        if n:
            self._map_hint.setText(
                f"{n} account{'s' if n != 1 else ''} selected  —  click a tax line to map"
            )
            self._map_hint.setStyleSheet(
                "color: #1A2B4C; font-style: italic; font-size: 11px; font-weight: bold;"
            )
        else:
            self._map_hint.setText("← Select accounts, then click a tax line to map")
            self._map_hint.setStyleSheet(
                "color: #888888; font-style: italic; font-size: 11px;"
            )

    def _on_acct_context_menu(self, pos):
        item = self._acct_tree.itemAt(pos)
        if not item:
            return
        selected = self._acct_tree.selectedItems()
        if not selected:
            self._acct_tree.setCurrentItem(item)
            selected = [item]
        count = len(selected)
        menu = QMenu(self)
        del_action = menu.addAction(f"Delete {count} Account{'s' if count != 1 else ''}…")
        if menu.exec(self._acct_tree.viewport().mapToGlobal(pos)) == del_action:
            self._on_delete_selected()

    def _on_delete_selected(self):
        selected = self._acct_tree.selectedItems()
        if not selected:
            return
        account_ids = [it.data(0, Qt.UserRole) for it in selected]
        names       = [it.text(_ACCOUNT_COL_NAME) for it in selected]
        count = len(account_ids)
        preview = "\n".join(f"  • {n}" for n in names[:10])
        if len(names) > 10:
            preview += f"\n  … and {len(names) - 10} more"
        reply = QMessageBox.warning(
            self, f"Delete {count} Account{'s' if count != 1 else ''}",
            f"Permanently delete {count} account{'s' if count != 1 else ''}?\n\n"
            f"{preview}\n\n"
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
                f"Deleted {len(deleted)}, skipped {len(blocked)} (have journal entry lines):\n"
                + "\n".join(f"  • {n}" for n in blocked),
            )
        # Refresh the left panel
        deleted_set = set(account_ids) if not blocked else set()
        with db_connection(self._path) as conn:
            rows = conn.execute(
                "SELECT account_id FROM accounts WHERE job_id = ?", (self._job_id,)
            ).fetchall()
        existing = {r[0] for r in rows}
        self._all_accounts = [a for a in self._all_accounts if a["account_id"] in existing]
        self._acct_search.clear()
        self._populate_accounts(self._all_accounts)

    def _on_line_clicked(self, item: QTreeWidgetItem, _col: int):
        template = item.data(0, Qt.UserRole)
        if not template:
            return  # group header

        selected = self._acct_tree.selectedItems()
        if not selected:
            return

        account_ids = [it.data(0, Qt.UserRole) for it in selected]

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
                account_ids=account_ids,
                tax_line_id=tax_line_id,
                mapped_by=self._performed_by,
            )
            log_activity(
                conn,
                job_id=self._job_id,
                event_type="changed_mapping",
                description=(
                    f"Mapped {len(account_ids)} account(s) to "
                    f"{template['line_name']} ({template['financial_statement']})"
                ),
                performed_by=self._performed_by,
            )

        self._mapped_count += len(account_ids)
        self._mapped_lbl.setText(f"✓  {self._mapped_count} account{'s' if self._mapped_count != 1 else ''} mapped this session")

        # remove mapped accounts from the left list
        mapped_set = set(account_ids)
        self._all_accounts = [a for a in self._all_accounts if a["account_id"] not in mapped_set]
        self._acct_search.clear()
        self._populate_accounts(self._all_accounts)


def _list_style(clickable: bool = False) -> str:
    hover = "QTreeWidget::item:hover:!selected { background: #D0D8E8; }" if clickable else ""
    return f"""
        QTreeWidget {{
            font-family: "Segoe UI";
            font-size: 13px;
            background: #FFFFFF;
            color: #000000;
            alternate-background-color: #F5F5F5;
            border: 1px solid #E5E5E5;
        }}
        QTreeWidget::item {{ padding: 4px 6px; }}
        QTreeWidget::item:selected {{
            background: #1A2B4C;
            color: #FFFFFF;
        }}
        QHeaderView::section {{
            background: #1A2B4C;
            color: #FFFFFF;
            font-family: "Segoe UI";
            font-size: 11px;
            font-weight: bold;
            letter-spacing: 1px;
            padding: 4px 6px;
            border: 1px solid #0f1d33;
        }}
        {hover}
    """
