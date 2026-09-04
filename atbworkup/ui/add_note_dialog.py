"""Dialog for adding a note (preparer / reviewer / delivery)."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QDialogButtonBox, QPushButton, QButtonGroup,
)
from PySide6.QtCore import Qt

from atbworkup.constants import NOTE_TYPE_COLORS

_TYPES_BY_ROLE: dict[str, list[tuple[str, str]]] = {
    # role → [(label, note_type), ...]  first entry is the default
    "preparer": [("Preparer",    "preparer")],
    "reviewer": [("Reviewer R",  "reviewer"),
                 ("Delivery",    "delivery")],
    "signer":   [("Preparer",    "preparer"),
                 ("Reviewer R",  "reviewer"),
                 ("Delivery",    "delivery")],
}


class AddNoteDialog(QDialog):
    def __init__(self, context_label: str, role: str = "preparer", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Note")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        lbl = QLabel(f"Note for: <b>{context_label}</b>")
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        # Type toggle — only show types allowed for this role
        options = _TYPES_BY_ROLE.get(role, _TYPES_BY_ROLE["preparer"])
        type_row = QHBoxLayout()
        type_row.addWidget(QLabel("Type:"))
        grp = QButtonGroup(self)
        grp.setExclusive(True)
        self._type_btns: list[tuple[str, QPushButton]] = []
        for i, (label, ntype) in enumerate(options):
            btn = _type_btn(label, checked=(i == 0),
                            active_color=NOTE_TYPE_COLORS.get(ntype, "#444444"))
            grp.addButton(btn)
            type_row.addWidget(btn)
            self._type_btns.append((ntype, btn))
        type_row.addStretch()
        layout.addLayout(type_row)

        self._body = QTextEdit()
        self._body.setPlaceholderText("Enter note…")
        self._body.setMinimumHeight(100)
        layout.addWidget(self._body)

        btns = QDialogButtonBox()
        self._add_btn = QPushButton("Add Note")
        self._add_btn.setDefault(True)
        self._add_btn.setEnabled(False)
        cancel = QPushButton("Cancel")
        cancel.setStyleSheet("background: #E5E5E5; color: #000000;")
        btns.addButton(self._add_btn, QDialogButtonBox.AcceptRole)
        btns.addButton(cancel, QDialogButtonBox.RejectRole)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self._body.textChanged.connect(
            lambda: self._add_btn.setEnabled(bool(self._body.toPlainText().strip()))
        )
        self._body.setFocus()

    def note_text(self) -> str:
        return self._body.toPlainText().strip()

    def note_type(self) -> str:
        for ntype, btn in self._type_btns:
            if btn.isChecked():
                return ntype
        return self._type_btns[0][0] if self._type_btns else "preparer"


def _type_btn(label: str, checked: bool, active_color: str) -> QPushButton:
    btn = QPushButton(label)
    btn.setCheckable(True)
    btn.setChecked(checked)
    btn.setFixedHeight(24)
    btn.setStyleSheet(f"""
        QPushButton {{
            background: #E5E5E5; color: #555555;
            font-size: 11px; border: 1px solid #CCCCCC;
            border-radius: 3px; padding: 0 10px;
        }}
        QPushButton:checked {{
            background: {active_color}; color: #FFFFFF; font-weight: bold;
            border-color: {active_color};
        }}
    """)
    return btn
