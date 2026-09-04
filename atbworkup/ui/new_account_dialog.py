"""
Inline account creation dialog.

Creates a single account directly in the binder without requiring an Excel import.
Optionally opens the mapping dialog after creation so the account can be
assigned to a tax line immediately.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLineEdit,
    QComboBox, QDoubleSpinBox, QVBoxLayout, QLabel,
    QCheckBox, QMessageBox,
)
from PySide6.QtCore import Qt

from atbworkup.db.connection import db_connection
from atbworkup.models.accounts import create_account

_ACCOUNT_TYPES = [
    ("Asset",     "Debit"),
    ("Liability", "Credit"),
    ("Equity",    "Credit"),
    ("Revenue",   "Credit"),
    ("Expense",   "Debit"),
]

# Normal balance override options
_NB_OPTIONS = ["Debit", "Credit"]


class NewAccountDialog(QDialog):
    """
    Minimal dialog to add one account inline.

    Fields:
      Account #      — optional, free text
      Account Name   — required
      Account Type   — Asset / Liability / Equity / Revenue / Expense
      Normal Balance — auto-set from type, override allowed
      PBC Balance    — numeric, default 0 (DR+ / CR-)
      Map after save — checkbox; if checked, opens MappingDialog on accept
    """

    def __init__(self, path: str | Path, job_id: str,
                 entity_type: str, performed_by: str,
                 parent=None):
        super().__init__(parent)
        self._path        = Path(path)
        self._job_id      = job_id
        self._entity_type = entity_type
        self._performed_by = performed_by
        self._new_account_id: str | None = None
        self.setWindowTitle("Add Account")
        self.setMinimumWidth(400)
        self._build_ui()

    def _build_ui(self):
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self._acct_num = QLineEdit()
        self._acct_num.setPlaceholderText("e.g. 1001")
        form.addRow("Account #", self._acct_num)

        self._acct_name = QLineEdit()
        self._acct_name.setPlaceholderText("e.g. Cash and Cash Equivalents")
        form.addRow("Account Name *", self._acct_name)

        self._acct_type = QComboBox()
        for atype, _ in _ACCOUNT_TYPES:
            self._acct_type.addItem(atype, userData=atype)
        self._acct_type.currentIndexChanged.connect(self._on_type_changed)
        form.addRow("Account Type *", self._acct_type)

        self._normal_balance = QComboBox()
        for nb in _NB_OPTIONS:
            self._normal_balance.addItem(nb, userData=nb)
        form.addRow("Normal Balance", self._normal_balance)

        self._pbc = QDoubleSpinBox()
        self._pbc.setRange(-999_999_999, 999_999_999)
        self._pbc.setDecimals(2)
        self._pbc.setValue(0.0)
        self._pbc.setGroupSeparatorShown(True)
        note = QLabel("DR = positive  |  CR = negative")
        note.setStyleSheet("font-size: 10px; color: #888;")
        form.addRow("PBC Balance", self._pbc)
        form.addRow("", note)

        self._map_after = QCheckBox("Map to tax line after saving")
        self._map_after.setChecked(True)

        self._error = QLabel("")
        self._error.setStyleSheet("color: red; font-size: 11px;")
        self._error.setVisible(False)

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._map_after)
        layout.addWidget(self._error)
        layout.addWidget(btns)

        # Initialize normal balance from default type (Asset → Debit)
        self._on_type_changed(0)

    def _on_type_changed(self, idx: int):
        atype = self._acct_type.itemData(idx)
        default_nb = dict(_ACCOUNT_TYPES).get(atype, "Debit")
        nb_idx = self._normal_balance.findData(default_nb)
        if nb_idx >= 0:
            self._normal_balance.setCurrentIndex(nb_idx)

    def _on_accept(self):
        name = self._acct_name.text().strip()
        if not name:
            self._error.setText("Account Name is required.")
            self._error.setVisible(True)
            return

        acct_num  = self._acct_num.text().strip() or None
        atype     = self._acct_type.currentData()
        nb        = self._normal_balance.currentData()
        pbc       = self._pbc.value()

        with db_connection(self._path) as conn:
            self._new_account_id = create_account(
                conn, self._job_id,
                account_number = acct_num or "",
                account_name   = name,
                account_type   = atype,
                normal_balance = nb,
                pbc_balance    = pbc,
            )

        self.accept()

        if self._map_after.isChecked() and self._new_account_id:
            from atbworkup.ui.mapping_dialog import MappingDialog
            dlg = MappingDialog(
                self._path, self._job_id, self._entity_type,
                [self._new_account_id], [name],
                self._performed_by, parent=self.parent(),
            )
            dlg.exec()

    def new_account_id(self) -> str | None:
        return self._new_account_id
