from __future__ import annotations

import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QComboBox, QSpinBox,
    QPushButton, QVBoxLayout, QWidget,
)
from PySide6.QtCore import Qt

from atbworkup.constants import get_entity_types
from atbworkup.utils.naming import suggested_filename


class NewWorkupDialog(QDialog):
    """Collects metadata for a new .atbw workup file."""

    def __init__(self, parent=None, force_entity_type: str | None = None):
        super().__init__(parent)
        self._force_entity_type = force_entity_type
        title = "Create New Consolidated Binder" if force_entity_type == "Consolidated" \
                else "Create New Workup"
        self.setWindowTitle(title)
        self.setMinimumWidth(480)
        self._build_ui()
        self._prefill_from_profile()
        if force_entity_type:
            for i in range(self._entity_type.count()):
                if self._entity_type.itemData(i) == force_entity_type:
                    self._entity_type.setCurrentIndex(i)
                    self._entity_type.setEnabled(False)
                    break

    def _prefill_from_profile(self):
        try:
            from atbworkup.db.settings import get_active_profile
            profile = get_active_profile()
            if profile and profile.get("display_name"):
                self._prepared_by.setText(profile["display_name"])
        except Exception:
            pass

    def _build_ui(self):
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self._client_name = QLineEdit()
        self._client_name.setPlaceholderText("ABC Company")
        form.addRow("Client Name *", self._client_name)

        self._entity_name = QLineEdit()
        self._entity_name.setPlaceholderText("ABC Company LLC")
        form.addRow("Entity Name *", self._entity_name)

        self._tax_year = QSpinBox()
        self._tax_year.setRange(2000, 2099)
        self._tax_year.setValue(datetime.date.today().year - 1)
        form.addRow("Tax Year *", self._tax_year)

        self._entity_type = QComboBox()
        for code, label in get_entity_types():
            self._entity_type.addItem(label, userData=code)
        form.addRow("Entity Type *", self._entity_type)

        self._prepared_by = QLineEdit()
        self._prepared_by.setPlaceholderText("Your name")
        form.addRow("Prepared By *", self._prepared_by)

        self._reviewer = QLineEdit()
        self._reviewer.setPlaceholderText("Optional")
        form.addRow("Reviewer", self._reviewer)

        self._accounting_system = QLineEdit()
        self._accounting_system.setPlaceholderText("QuickBooks, Xero, etc.")
        form.addRow("Accounting System", self._accounting_system)

        # Workpaper folder row (text + browse button)
        folder_row = QWidget()
        folder_layout = QHBoxLayout(folder_row)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        self._folder_path = QLineEdit()
        self._folder_path.setPlaceholderText("Select folder…")
        browse_btn = QPushButton("Browse…")
        browse_btn.setFixedWidth(80)
        browse_btn.clicked.connect(self._browse_folder)
        folder_layout.addWidget(self._folder_path)
        folder_layout.addWidget(browse_btn)
        form.addRow("Workpaper Folder *", folder_row)

        self._error_label = QLabel("")
        self._error_label.setStyleSheet("color: red;")
        self._error_label.setVisible(False)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._error_label)
        layout.addWidget(buttons)

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Workpaper Folder")
        if folder:
            self._folder_path.setText(folder)

    def _on_accept(self):
        errors = []
        if not self._client_name.text().strip():
            errors.append("Client Name is required.")
        if not self._entity_name.text().strip():
            errors.append("Entity Name is required.")
        if not self._prepared_by.text().strip():
            errors.append("Prepared By is required.")
        if not self._folder_path.text().strip():
            errors.append("Workpaper Folder is required.")
        elif not Path(self._folder_path.text().strip()).is_dir():
            errors.append("Workpaper Folder does not exist.")

        if errors:
            self._error_label.setText("\n".join(errors))
            self._error_label.setVisible(True)
            return

        self._error_label.setVisible(False)
        self.accept()

    def metadata(self) -> dict:
        """Return validated metadata dict. Call only after accept()."""
        folder = self._folder_path.text().strip()
        client = self._client_name.text().strip()
        year = self._tax_year.value()
        return {
            "client_name": client,
            "entity_name": self._entity_name.text().strip(),
            "tax_year": year,
            "entity_type": self._entity_type.currentData(),
            "prepared_by": self._prepared_by.text().strip(),
            "reviewer": self._reviewer.text().strip() or None,
            "workpaper_folder": folder,
            "accounting_system": self._accounting_system.text().strip() or None,
            "suggested_filename": suggested_filename(year, client),
        }
