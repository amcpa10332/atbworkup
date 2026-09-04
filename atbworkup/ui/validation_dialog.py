"""
Pre-export validation dialog.

Shows each check with ✓ / ✗ and detail text.
Export button only enabled when all checks pass.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QWidget, QDialogButtonBox,
)
from PySide6.QtCore import Qt


class ValidationDialog(QDialog):

    def __init__(self, results: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Validation — Ready for Review")
        self.setMinimumWidth(520)
        self._results = results
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        from atbworkup.models.validation import all_pass
        passed = all_pass(self._results)

        # summary banner
        if passed:
            banner = QLabel("All checks passed. Ready to export.")
            banner.setStyleSheet(
                "background: #e8f5e9; color: #2e7d32; font-weight: bold; "
                "padding: 8px 12px; border-radius: 3px;"
            )
        else:
            n_fail = sum(1 for r in self._results if r["status"] == "fail")
            banner = QLabel(f"{n_fail} check{'s' if n_fail != 1 else ''} failed. Fix issues before exporting.")
            banner.setStyleSheet(
                "background: #ffebee; color: #C62828; font-weight: bold; "
                "padding: 8px 12px; border-radius: 3px;"
            )
        banner.setWordWrap(True)
        layout.addWidget(banner)

        # check list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setSpacing(4)
        inner_layout.setContentsMargins(0, 0, 0, 0)

        for r in self._results:
            inner_layout.addWidget(_CheckRow(r))

        inner_layout.addStretch()
        scroll.setWidget(inner)
        layout.addWidget(scroll, 1)

        # buttons
        btn_box = QDialogButtonBox()
        self._export_btn = QPushButton("Export Package")
        self._export_btn.setEnabled(passed)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(
            "background: #E5E5E5; color: #000000; font-weight: normal;"
        )
        btn_box.addButton(self._export_btn, QDialogButtonBox.AcceptRole)
        btn_box.addButton(cancel_btn,       QDialogButtonBox.RejectRole)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)


class _CheckRow(QFrame):
    def __init__(self, result: dict, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        status = result["status"]
        bg = {"pass": "#f1f8e9", "warn": "#fff8e1", "fail": "#ffebee"}.get(status, "#FFFFFF")
        self.setStyleSheet(f"QFrame {{ background: {bg}; border: 1px solid #E5E5E5; border-radius: 3px; }}")

        hl = QHBoxLayout(self)
        hl.setContentsMargins(10, 6, 10, 6)

        icon = {"pass": "✓", "warn": "⚠", "fail": "✗"}.get(status, "?")
        color = {"pass": "#2e7d32", "warn": "#e65100", "fail": "#C62828"}.get(status, "#000")
        icon_lbl = QLabel(icon)
        icon_lbl.setFixedWidth(20)
        icon_lbl.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 14px; background: transparent; border: none;")
        hl.addWidget(icon_lbl)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        label_lbl = QLabel(result["label"])
        label_lbl.setStyleSheet(f"font-weight: bold; color: {color}; background: transparent; border: none;")
        text_layout.addWidget(label_lbl)
        if result.get("detail"):
            detail_lbl = QLabel(result["detail"])
            detail_lbl.setWordWrap(True)
            detail_lbl.setStyleSheet("color: #555555; font-size: 11px; background: transparent; border: none;")
            text_layout.addWidget(detail_lbl)
        hl.addLayout(text_layout, 1)
