"""
Role selection dialog — shown the first time a user opens a specific package.
Lets the user declare Preparer / Reviewer / Signer and optionally remember it.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox,
)
from PySide6.QtCore import Qt

from atbworkup.constants import ROLE_COLORS

_ROLES = [
    ("Preparer", "preparer", ROLE_COLORS["preparer"]),
    ("Reviewer", "reviewer", ROLE_COLORS["reviewer"]),
    ("Signer",   "signer",   ROLE_COLORS["signer"]),
]


class RoleDialog(QDialog):
    """Ask the current user their role on a specific package."""

    def __init__(self, client_name: str, tax_year: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Your Role")
        self.setMinimumWidth(380)
        self._role: str | None = None
        self._build_ui(client_name, tax_year)

    def _build_ui(self, client_name: str, tax_year: int):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        lbl = QLabel(
            f"<b>What is your role on</b><br>"
            f"<span style='font-size:13px;'>{client_name} — {tax_year}?</span>"
        )
        lbl.setTextFormat(Qt.RichText)
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        for label, role_key, color in _ROLES:
            btn = QPushButton(label)
            btn.setFixedHeight(42)
            btn.setStyleSheet(
                f"QPushButton {{ background: {color}; color: #FFFFFF; font-weight: bold; "
                f"font-size: 13px; border-radius: 4px; }}"
                f"QPushButton:hover {{ opacity: 0.85; }}"
            )
            btn.clicked.connect(lambda checked=False, r=role_key: self._select(r))
            btn_row.addWidget(btn)
        layout.addLayout(btn_row)

        self._remember_chk = QCheckBox("Remember my role for this file")
        self._remember_chk.setChecked(True)
        layout.addWidget(self._remember_chk)

    def _select(self, role: str):
        self._role = role
        self.accept()

    def role(self) -> str | None:
        return self._role

    def should_remember(self) -> bool:
        return self._remember_chk.isChecked()
