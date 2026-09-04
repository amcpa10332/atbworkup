"""
Rollforward wizard dialog.

Step 1 — Prior year file:
  File picker + read-only summary of the prior year package.

Step 2 — New year setup:
  Pre-filled metadata form (tax_year = prior + 1, same client/entity/type).
  Editable: tax_year, prepared_by, reviewer, workpaper folder, accounting system.

OK button only enabled after a valid prior year package is loaded.
"""
from __future__ import annotations

import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QPushButton, QSpinBox, QVBoxLayout, QWidget, QFrame,
)
from PySide6.QtCore import Qt

from atbworkup.constants import ENTITY_TYPES
from atbworkup.utils.naming import suggested_filename
from atbworkup.models.rollforward import read_prior_year_summary


class RollforwardDialog(QDialog):
    """
    Returns a metadata dict (same shape as NewWorkupDialog.metadata()) on accept.
    Also exposes `prior_xlsx_path()` for the caller to pass to create_rollforward().
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Rollforward from Prior Year")
        self.setMinimumWidth(520)
        self._prior_path: Path | None = None
        self._prior_summary: dict = {}
        self._build_ui()
        self._prefill_from_profile()

    # ── Public ────────────────────────────────────────────────────────────

    def prior_xlsx_path(self) -> Path | None:
        return self._prior_path

    def metadata(self) -> dict:
        folder = self._folder.text().strip()
        client = self._prior_summary.get("client_name", "")
        year   = self._tax_year.value()
        return {
            "client_name":      client,
            "entity_name":      self._prior_summary.get("entity_name", ""),
            "tax_year":         year,
            "entity_type":      self._prior_summary.get("entity_type", ""),
            "prepared_by":      self._prepared_by.text().strip(),
            "reviewer":         self._reviewer.text().strip() or None,
            "workpaper_folder": folder,
            "accounting_system": self._prior_summary.get("accounting_system") or None,
            "suggested_filename": suggested_filename(year, client),
        }

    # ── Build ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # ── Prior year section ────────────────────────────────────────────
        prior_box = QGroupBox("Prior Year Package")
        prior_lay = QVBoxLayout(prior_box)

        file_row = QHBoxLayout()
        self._file_lbl = QLabel("No file selected")
        self._file_lbl.setStyleSheet("color: #666666; font-style: italic;")
        self._file_lbl.setWordWrap(True)
        browse_btn = QPushButton("Select .atbr.xlsx…")
        browse_btn.setFixedWidth(160)
        browse_btn.clicked.connect(self._browse_prior)
        file_row.addWidget(self._file_lbl, 1)
        file_row.addWidget(browse_btn)
        prior_lay.addLayout(file_row)

        self._summary_widget = QWidget()
        summary_form = QFormLayout(self._summary_widget)
        summary_form.setLabelAlignment(Qt.AlignRight)
        summary_form.setContentsMargins(0, 4, 0, 0)

        self._sum_client = QLabel("—")
        self._sum_entity = QLabel("—")
        self._sum_year   = QLabel("—")
        self._sum_counts = QLabel("—")
        for lbl in (self._sum_client, self._sum_entity, self._sum_year, self._sum_counts):
            lbl.setStyleSheet("font-weight: bold;")

        summary_form.addRow("Client:", self._sum_client)
        summary_form.addRow("Entity:", self._sum_entity)
        summary_form.addRow("Tax Year:", self._sum_year)
        summary_form.addRow("Accounts / Mappings:", self._sum_counts)
        self._summary_widget.setVisible(False)
        prior_lay.addWidget(self._summary_widget)

        self._error_lbl = QLabel("")
        self._error_lbl.setStyleSheet("color: #CC0000; font-size: 11px;")
        self._error_lbl.setVisible(False)
        prior_lay.addWidget(self._error_lbl)

        layout.addWidget(prior_box)

        # Divider
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #DDDDDD;")
        layout.addWidget(sep)

        # ── New year section ──────────────────────────────────────────────
        new_box = QGroupBox("New Year Settings")
        new_form = QFormLayout(new_box)
        new_form.setLabelAlignment(Qt.AlignRight)
        new_form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self._tax_year = QSpinBox()
        self._tax_year.setRange(2000, 2099)
        self._tax_year.setValue(datetime.date.today().year)
        new_form.addRow("Tax Year *", self._tax_year)

        self._prepared_by = QLineEdit()
        self._prepared_by.setPlaceholderText("Your name")
        new_form.addRow("Prepared By *", self._prepared_by)

        self._reviewer = QLineEdit()
        self._reviewer.setPlaceholderText("Optional")
        new_form.addRow("Reviewer", self._reviewer)

        folder_row = QWidget()
        folder_layout = QHBoxLayout(folder_row)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        self._folder = QLineEdit()
        self._folder.setPlaceholderText("Select folder…")
        folder_browse = QPushButton("Browse…")
        folder_browse.setFixedWidth(80)
        folder_browse.clicked.connect(self._browse_folder)
        folder_layout.addWidget(self._folder)
        folder_layout.addWidget(folder_browse)
        new_form.addRow("Workpaper Folder *", folder_row)

        layout.addWidget(new_box)

        # ── Info note ─────────────────────────────────────────────────────
        note = QLabel(
            "Balance Sheet accounts carry their prior year closing adjusted balance "
            "as the new PBC.  P&L accounts reset to zero.  Journal entries and notes "
            "do not carry forward."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #555555; font-size: 11px; padding: 4px 0;")
        layout.addWidget(note)

        # ── Buttons ───────────────────────────────────────────────────────
        self._form_error = QLabel("")
        self._form_error.setStyleSheet("color: red;")
        self._form_error.setVisible(False)
        layout.addWidget(self._form_error)

        self._buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self._buttons.button(QDialogButtonBox.Ok).setEnabled(False)
        self._buttons.accepted.connect(self._on_accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    def _prefill_from_profile(self):
        try:
            from atbworkup.db.settings import get_active_profile
            profile = get_active_profile()
            if profile and profile.get("display_name"):
                self._prepared_by.setText(profile["display_name"])
        except Exception:
            pass

    # ── Slots ─────────────────────────────────────────────────────────────

    def _browse_prior(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Prior Year Review Package",
            "", "TB Workup Files (*.atbr.xlsx);;All Files (*)",
        )
        if not path:
            return
        self._load_prior(Path(path))

    def _load_prior(self, path: Path):
        self._error_lbl.setVisible(False)
        self._summary_widget.setVisible(False)
        self._buttons.button(QDialogButtonBox.Ok).setEnabled(False)

        try:
            summary = read_prior_year_summary(path)
        except ValueError as exc:
            self._error_lbl.setText(str(exc))
            self._error_lbl.setVisible(True)
            return

        self._prior_path    = path
        self._prior_summary = summary

        self._file_lbl.setText(path.name)
        self._file_lbl.setStyleSheet("color: #1A2B4C; font-style: normal; font-weight: bold;")

        prior_year = summary.get("tax_year", 0) or 0
        self._sum_client.setText(summary.get("client_name", "—"))
        self._sum_entity.setText(summary.get("entity_name", "—"))
        self._sum_year.setText(str(prior_year))
        self._sum_counts.setText(
            f"{summary.get('account_count', 0)} accounts  /  "
            f"{summary.get('mapping_count', 0)} mappings"
        )
        self._summary_widget.setVisible(True)

        # Pre-fill new year
        if prior_year:
            self._tax_year.setValue(prior_year + 1)

        # Pre-fill folder to same folder as the prior package
        if not self._folder.text().strip():
            self._folder.setText(str(path.parent))

        self._buttons.button(QDialogButtonBox.Ok).setEnabled(True)

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Workpaper Folder")
        if folder:
            self._folder.setText(folder)

    def _on_accept(self):
        errors = []
        if not self._prepared_by.text().strip():
            errors.append("Prepared By is required.")
        folder_str = self._folder.text().strip()
        if not folder_str:
            errors.append("Workpaper Folder is required.")
        elif not Path(folder_str).is_dir():
            errors.append("Workpaper Folder does not exist.")
        if errors:
            self._form_error.setText("\n".join(errors))
            self._form_error.setVisible(True)
            return
        self._form_error.setVisible(False)
        self.accept()
