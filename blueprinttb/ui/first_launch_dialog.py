"""
First-launch profile setup dialog — shown once when no user profile exists.
Stores name and initials in the settings DB via save_profile().
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit,
    QLabel, QPushButton,
)
from PySide6.QtCore import Qt


def _auto_initials(name: str) -> str:
    parts = name.strip().split()
    return "".join(p[0].upper() for p in parts if p)[:3]


class FirstLaunchDialog(QDialog):
    """One-time profile setup. Non-cancellable — must fill name + initials."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Welcome to TB Workup — Set Up Your Profile")
        self.setMinimumWidth(420)
        self.setWindowFlag(Qt.WindowCloseButtonHint, False)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        welcome = QLabel(
            "<b style='font-size:14px;'>Set up your profile</b><br><br>"
            "<span style='color:#555555;'>Your name and initials identify your work "
            "across all packages. You'll only need to enter this once.</span>"
        )
        welcome.setWordWrap(True)
        welcome.setTextFormat(Qt.RichText)
        layout.addWidget(welcome)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        form.setVerticalSpacing(8)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. Austin Malone")
        form.addRow("Full Name *", self._name_edit)

        self._initials_edit = QLineEdit()
        self._initials_edit.setMaxLength(3)
        self._initials_edit.setPlaceholderText("e.g. AM")
        form.addRow("Initials *", self._initials_edit)

        layout.addLayout(form)

        self._error_lbl = QLabel("")
        self._error_lbl.setStyleSheet("color: #CC0000;")
        self._error_lbl.setVisible(False)
        layout.addWidget(self._error_lbl)

        ok_btn = QPushButton("Get Started")
        ok_btn.setFixedHeight(38)
        ok_btn.setStyleSheet(
            "background: #1A2B4C; color: #FFFFFF; font-weight: bold; "
            "font-size: 13px; border-radius: 4px;"
        )
        ok_btn.clicked.connect(self._on_ok)
        layout.addWidget(ok_btn)

        self._name_edit.textChanged.connect(self._sync_initials)
        self._name_edit.setFocus()

    def _sync_initials(self, text: str):
        self._initials_edit.setText(_auto_initials(text))

    def _on_ok(self):
        name     = self._name_edit.text().strip()
        initials = self._initials_edit.text().strip().upper()
        if not name:
            self._show_error("Full name is required.")
            return
        if not initials:
            self._show_error("Initials are required.")
            return
        self._error_lbl.setVisible(False)
        self.accept()

    def _show_error(self, msg: str):
        self._error_lbl.setText(msg)
        self._error_lbl.setVisible(True)

    def display_name(self) -> str:
        return self._name_edit.text().strip()

    def initials(self) -> str:
        return self._initials_edit.text().strip().upper()
