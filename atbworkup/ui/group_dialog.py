"""
Group picker dialog — assign selected accounts to an existing or new group.

Layout:
  - Accounts being grouped (read-only label)
  - Tree of existing groups (select one to add to)
  - ── or create new ──
  - Name field + optional parent group dropdown
  - OK / Cancel
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QTreeWidget, QTreeWidgetItem,
    QDialogButtonBox, QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt

from atbworkup.db.connection import db_connection
from atbworkup.models.groups import get_groups, create_group


class GroupPickerDialog(QDialog):
    """
    Pick an existing group or create a new one, then return its group_id.
    Call `chosen_group_id()` after Accepted.
    """

    def __init__(
        self,
        path: str | Path,
        job_id: str,
        account_ids: list[str],
        account_names: list[str],
        parent=None,
    ):
        super().__init__(parent)
        self._path = Path(path)
        self._job_id = job_id
        self._account_ids = account_ids
        self._chosen_group_id: str | None = None

        self.setWindowTitle("Add to Group")
        self.setMinimumWidth(420)
        self._build_ui(account_names)
        self._load_groups()

    # ── Public ────────────────────────────────────────────────────────────

    def chosen_group_id(self) -> str | None:
        return self._chosen_group_id

    # ── Build UI ──────────────────────────────────────────────────────────

    def _build_ui(self, account_names: list[str]):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Accounts summary
        names_str = ", ".join(account_names[:5])
        if len(account_names) > 5:
            names_str += f"  (+{len(account_names) - 5} more)"
        lbl = QLabel(f"Grouping:  {names_str}")
        lbl.setWordWrap(True)
        lbl.setStyleSheet("color: #555; font-size: 12px; padding: 4px 0;")
        layout.addWidget(lbl)

        # Existing groups tree
        layout.addWidget(QLabel("Add to existing group:"))
        self._group_tree = QTreeWidget()
        self._group_tree.setHeaderHidden(True)
        self._group_tree.setRootIsDecorated(True)
        self._group_tree.setFixedHeight(160)
        self._group_tree.itemSelectionChanged.connect(self._on_existing_selected)
        layout.addWidget(self._group_tree)

        # Divider
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #CCC;")
        layout.addWidget(sep)
        layout.addWidget(QLabel("— or create new group —"))

        # New group name
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Name:"))
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. Property Taxes")
        self._name_edit.textChanged.connect(self._on_new_name_changed)
        name_row.addWidget(self._name_edit)
        layout.addLayout(name_row)

        # Parent group
        parent_row = QHBoxLayout()
        parent_row.addWidget(QLabel("Under:"))
        self._parent_combo = QComboBox()
        self._parent_combo.addItem("(top level)", None)
        parent_row.addWidget(self._parent_combo)
        layout.addLayout(parent_row)

        # Buttons
        self._buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        self._buttons.accepted.connect(self._on_ok)
        self._buttons.rejected.connect(self.reject)
        self._buttons.button(QDialogButtonBox.Ok).setEnabled(False)
        layout.addWidget(self._buttons)

    # ── Load data ─────────────────────────────────────────────────────────

    def _load_groups(self):
        with db_connection(self._path) as conn:
            groups = get_groups(conn, self._job_id)

        self._all_groups = {g["group_id"]: g for g in groups}

        # Populate tree
        self._group_tree.clear()
        self._tree_items: dict[str, QTreeWidgetItem] = {}

        def _add(gid: str, parent_item=None):
            g = self._all_groups[gid]
            item = QTreeWidgetItem([g["name"]])
            item.setData(0, Qt.UserRole, gid)
            if parent_item is None:
                self._group_tree.addTopLevelItem(item)
            else:
                parent_item.addChild(item)
            self._tree_items[gid] = item
            # Add children
            for child in groups:
                if child["parent_id"] == gid:
                    _add(child["group_id"], item)

        for g in groups:
            if g["parent_id"] is None:
                _add(g["group_id"])

        self._group_tree.expandAll()

        # Populate parent combo for new group
        self._parent_combo.clear()
        self._parent_combo.addItem("(top level)", None)
        for g in groups:
            self._parent_combo.addItem(g["name"], g["group_id"])

    # ── Slot helpers ──────────────────────────────────────────────────────

    def _on_existing_selected(self):
        items = self._group_tree.selectedItems()
        has_selection = bool(items)
        # If an existing group is selected, enable OK and clear new-name field
        if has_selection:
            self._name_edit.blockSignals(True)
            self._name_edit.clear()
            self._name_edit.blockSignals(False)
        self._buttons.button(QDialogButtonBox.Ok).setEnabled(has_selection)

    def _on_new_name_changed(self, text: str):
        if text.strip():
            # Deselect existing group
            self._group_tree.clearSelection()
            self._buttons.button(QDialogButtonBox.Ok).setEnabled(True)
        else:
            has_selection = bool(self._group_tree.selectedItems())
            self._buttons.button(QDialogButtonBox.Ok).setEnabled(has_selection)

    def _on_ok(self):
        new_name = self._name_edit.text().strip()
        if new_name:
            # Create new group
            parent_id = self._parent_combo.currentData()
            with db_connection(self._path) as conn:
                self._chosen_group_id = create_group(conn, self._job_id, new_name, parent_id)
        else:
            items = self._group_tree.selectedItems()
            if items:
                self._chosen_group_id = items[0].data(0, Qt.UserRole)

        if self._chosen_group_id:
            self.accept()
