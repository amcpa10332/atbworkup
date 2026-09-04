"""
Trial Balance Import Wizard — 3 pages:

  Page 0 — File & Sheet:  pick .xlsx file, pick sheet
  Page 1 — Column Setup:  preview grid, header row, column assignments
  Page 2 — Confirm:       parsed counts, balance totals
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QWizard, QWizardPage,
    QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QComboBox,
    QSpinBox, QTableWidget, QTableWidgetItem,
    QFileDialog, QGroupBox,
    QSizePolicy, QMessageBox, QAbstractItemView,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont

from atbworkup.importer.tb_parser import (
    get_sheet_names, read_raw_rows, detect_header_row,
    parse_accounts, ParseResult,
)

PREVIEW_ROWS = 50
_NO_COL = "— none —"

_TOGGLE_ON = (
    "QPushButton { background: #1A2B4C; color: #FFFFFF; font-weight: bold; "
    "border: 2px solid #1A2B4C; border-radius: 3px; padding: 5px 14px; font-size: 12px; }"
)
_TOGGLE_OFF = (
    "QPushButton { background: #FFFFFF; color: #1A2B4C; font-weight: bold; "
    "border: 2px solid #1A2B4C; border-radius: 3px; padding: 5px 14px; font-size: 12px; }"
    "QPushButton:hover { background: #E8ECF4; }"
)


class TBImportWizard(QWizard):
    def __init__(self, parent=None, initial_dir: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Import Trial Balance")
        self.setMinimumSize(900, 640)
        self.setWizardStyle(QWizard.ModernStyle)
        self.setButtonText(QWizard.FinishButton, "Import")

        self._raw_rows: list[list[Any]] = []
        self._parse_result: ParseResult | None = None
        self._col_config: dict = {}
        self._initial_dir: str = initial_dir

        self._page_file = _FileSheetPage(self)
        self._page_cols = _ColumnSetupPage(self)
        self._page_confirm = _ConfirmPage(self)

        self.addPage(self._page_file)
        self.addPage(self._page_cols)
        self.addPage(self._page_confirm)

    def result_data(self) -> ParseResult | None:
        return self._parse_result

    def column_config(self) -> dict:
        return self._col_config


# ---------------------------------------------------------------------------
# Page 0 — File & Sheet
# ---------------------------------------------------------------------------

class _FileSheetPage(QWizardPage):
    def __init__(self, wizard: TBImportWizard):
        super().__init__(wizard)
        self._wiz = wizard
        self.setTitle("Select File")
        self.setSubTitle("Choose the Excel file that contains your trial balance.")
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        file_row = QHBoxLayout()
        self._file_edit = QLineEdit()
        self._file_edit.setPlaceholderText("No file selected…")
        self._file_edit.setReadOnly(True)
        browse = QPushButton("Browse…")
        browse.setFixedWidth(90)
        browse.clicked.connect(self._browse)
        file_row.addWidget(QLabel("File:"))
        file_row.addWidget(self._file_edit, 1)
        file_row.addWidget(browse)

        sheet_row = QHBoxLayout()
        self._sheet_combo = QComboBox()
        self._sheet_combo.setEnabled(False)
        self._sheet_combo.setMinimumWidth(200)
        sheet_row.addWidget(QLabel("Sheet:"))
        sheet_row.addWidget(self._sheet_combo)
        sheet_row.addStretch()

        layout.addLayout(file_row)
        layout.addLayout(sheet_row)
        layout.addStretch()

        self._sheet_combo.currentTextChanged.connect(self.completeChanged)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Trial Balance File", self._wiz._initial_dir,
            "Excel Files (*.xlsx *.xls);;All Files (*)",
        )
        if not path:
            return
        self._file_edit.setText(path)
        try:
            sheets = get_sheet_names(path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not read file:\n{e}")
            return
        self._sheet_combo.clear()
        self._sheet_combo.addItems(sheets)
        self._sheet_combo.setEnabled(True)
        self.completeChanged.emit()

    def isComplete(self) -> bool:
        return bool(self._file_edit.text()) and self._sheet_combo.count() > 0

    def validatePage(self) -> bool:
        try:
            rows = read_raw_rows(self._file_edit.text(), self._sheet_combo.currentText())
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not read sheet:\n{e}")
            return False
        self._wiz._raw_rows = rows
        return True

    @property
    def selected_path(self) -> str:
        return self._file_edit.text()

    @property
    def selected_sheet(self) -> str:
        return self._sheet_combo.currentText()


# ---------------------------------------------------------------------------
# Page 1 — Column Setup
# ---------------------------------------------------------------------------

class _ColumnSetupPage(QWizardPage):
    def __init__(self, wizard: TBImportWizard):
        super().__init__(wizard)
        self._wiz = wizard
        self._n_cols = 0
        self.setTitle("Assign Columns")
        self.setSubTitle(
            "Set the header row, then select which columns contain account data."
        )
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ── top controls ──────────────────────────────────────────────
        ctrl_group = QGroupBox("Column Assignments")
        grid = QGridLayout(ctrl_group)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        self._header_spin = QSpinBox()
        self._header_spin.setRange(1, 100)
        self._header_spin.setValue(1)
        self._header_spin.valueChanged.connect(self._on_header_changed)
        grid.addWidget(QLabel("Header row:"), 0, 0, Qt.AlignRight)
        grid.addWidget(self._header_spin, 0, 1)

        self._number_combo = QComboBox()
        self._number_combo.setMinimumWidth(220)
        grid.addWidget(QLabel("Account # column (optional):"), 1, 0, Qt.AlignRight)
        grid.addWidget(self._number_combo, 1, 1)

        self._name_combo = QComboBox()
        self._name_combo.setMinimumWidth(220)
        self._name_combo.currentIndexChanged.connect(self.completeChanged)
        grid.addWidget(QLabel("Account name column *:"), 2, 0, Qt.AlignRight)
        grid.addWidget(self._name_combo, 2, 1)

        # layout mode — navy toggle button selectors
        mode_lbl = QLabel("Balance layout:")
        mode_lbl.setStyleSheet("color: #1A2B4C; font-weight: bold;")
        grid.addWidget(mode_lbl, 0, 2, Qt.AlignRight)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(0)
        self._mode_single = QPushButton("Single Column")
        self._mode_two    = QPushButton("Debit / Credit")
        for btn in (self._mode_single, self._mode_two):
            btn.setCheckable(True)
            btn.setFixedHeight(32)
        self._mode_single.setChecked(True)
        self._mode_single.setStyleSheet(_TOGGLE_ON)
        self._mode_two.setStyleSheet(_TOGGLE_OFF)
        self._mode_single.clicked.connect(lambda: self._set_mode(True))
        self._mode_two.clicked.connect(lambda: self._set_mode(False))
        mode_row.addWidget(self._mode_single)
        mode_row.addWidget(self._mode_two)
        mode_row.addStretch()
        grid.addLayout(mode_row, 0, 3)

        self._balance_label = QLabel("Balance column *:")
        self._balance_combo = QComboBox()
        self._balance_combo.setMinimumWidth(220)
        self._balance_combo.currentIndexChanged.connect(self.completeChanged)
        grid.addWidget(self._balance_label, 3, 0, Qt.AlignRight)
        grid.addWidget(self._balance_combo, 3, 1)

        self._debit_label  = QLabel("Debit column *:")
        self._credit_label = QLabel("Credit column *:")
        self._debit_combo  = QComboBox()
        self._credit_combo = QComboBox()
        self._debit_combo.setMinimumWidth(220)
        self._credit_combo.setMinimumWidth(220)
        self._debit_combo.currentIndexChanged.connect(self.completeChanged)
        self._credit_combo.currentIndexChanged.connect(self.completeChanged)
        grid.addWidget(self._debit_label,  2, 2, Qt.AlignRight)
        grid.addWidget(self._debit_combo,  2, 3)
        grid.addWidget(self._credit_label, 3, 2, Qt.AlignRight)
        grid.addWidget(self._credit_combo, 3, 3)
        self._debit_label.setVisible(False)
        self._debit_combo.setVisible(False)
        self._credit_label.setVisible(False)
        self._credit_combo.setVisible(False)

        layout.addWidget(ctrl_group)

        # ── preview table ─────────────────────────────────────────────
        layout.addWidget(QLabel("Preview (first rows — header row highlighted in blue):"))
        self._preview = QTableWidget()
        self._preview.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._preview.setSelectionMode(QAbstractItemView.NoSelection)
        self._preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._preview.horizontalHeader().setDefaultSectionSize(110)
        self._preview.verticalHeader().setDefaultSectionSize(22)
        # Force light colors so the preview is readable in dark-themed Windows
        self._preview.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                color: #000000;
                gridline-color: #cccccc;
            }
            QTableWidget::item { color: #000000; background-color: #ffffff; }
            QHeaderView::section {
                background-color: #efefef;
                color: #000000;
                border: 1px solid #cccccc;
            }
        """)
        layout.addWidget(self._preview)

    # ------------------------------------------------------------------

    def initializePage(self):
        rows = self._wiz._raw_rows
        if not rows:
            return

        n_rows = min(PREVIEW_ROWS, len(rows))
        self._n_cols = max((len(r) for r in rows[:n_rows]), default=0)

        self._populate_preview(rows, n_rows)

        # Guess header row first (needs name col guess)
        best_name = _guess_name_col(rows, self._n_cols)
        if best_name >= 0:
            detected_header = detect_header_row(rows, best_name)
        else:
            detected_header = 0

        self._header_spin.blockSignals(True)
        self._header_spin.setValue(detected_header + 1)  # 1-based display
        self._header_spin.blockSignals(False)

        self._rebuild_combos(rows, detected_header)

        # Auto-select best guesses
        if best_name >= 0:
            self._name_combo.setCurrentIndex(best_name + 1)  # +1 for "— none —"
        best_bal = _guess_balance_col(rows, self._n_cols, best_name, detected_header)
        if best_bal >= 0:
            self._balance_combo.setCurrentIndex(best_bal + 1)

        self._highlight_header(detected_header)
        # Tell the wizard to re-check isComplete now that combos are set
        self.completeChanged.emit()

    def _populate_preview(self, rows, n_rows):
        self._preview.setRowCount(n_rows)
        self._preview.setColumnCount(self._n_cols)
        self._preview.setHorizontalHeaderLabels(
            [_col_letter(i) for i in range(self._n_cols)]
        )
        black = QColor("#000000")
        white = QColor("#ffffff")
        for r, row in enumerate(rows[:n_rows]):
            for c in range(self._n_cols):
                val = row[c] if c < len(row) else None
                if val is not None:
                    item = QTableWidgetItem(str(val))
                    item.setForeground(black)
                    item.setBackground(white)
                    self._preview.setItem(r, c, item)
        self._preview.resizeColumnsToContents()

    def _rebuild_combos(self, rows, header_row_0based: int):
        """Repopulate all column combos using header row cell values as labels."""
        header_row = rows[header_row_0based] if header_row_0based < len(rows) else []

        options = [_NO_COL]
        for i in range(self._n_cols):
            letter = _col_letter(i)
            cell = header_row[i] if i < len(header_row) else None
            label = f"{letter}: {cell}" if cell else letter
            options.append(label)

        prev = {
            self._number_combo:  self._number_combo.currentIndex(),
            self._name_combo:    self._name_combo.currentIndex(),
            self._balance_combo: self._balance_combo.currentIndex(),
            self._debit_combo:   self._debit_combo.currentIndex(),
            self._credit_combo:  self._credit_combo.currentIndex(),
        }
        for combo in prev:
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(options)
            combo.setCurrentIndex(min(prev[combo], len(options) - 1))
            combo.blockSignals(False)

    def _on_header_changed(self, value):
        rows = self._wiz._raw_rows
        if not rows:
            return
        header_0 = value - 1
        self._rebuild_combos(rows, header_0)
        self._highlight_header(header_0)
        self.completeChanged.emit()

    def _highlight_header(self, header_row_0: int):
        blue  = QColor("#cce5ff")
        white = QColor("#ffffff")
        black = QColor("#000000")
        for r in range(self._preview.rowCount()):
            bg = blue if r == header_row_0 else white
            for c in range(self._preview.columnCount()):
                item = self._preview.item(r, c)
                if item:
                    item.setBackground(bg)
                    item.setForeground(black)

    def _set_mode(self, single: bool):
        self._mode_single.setChecked(single)
        self._mode_two.setChecked(not single)
        self._mode_single.setStyleSheet(_TOGGLE_ON if single else _TOGGLE_OFF)
        self._mode_two.setStyleSheet(_TOGGLE_ON if not single else _TOGGLE_OFF)
        self._balance_label.setVisible(single)
        self._balance_combo.setVisible(single)
        self._debit_label.setVisible(not single)
        self._debit_combo.setVisible(not single)
        self._credit_label.setVisible(not single)
        self._credit_combo.setVisible(not single)
        self.completeChanged.emit()

    def isComplete(self) -> bool:
        if self._name_combo.currentText() == _NO_COL:
            return False
        if self._mode_single.isChecked():
            return self._balance_combo.currentText() != _NO_COL
        return (self._debit_combo.currentText() != _NO_COL
                and self._credit_combo.currentText() != _NO_COL)

    def validatePage(self) -> bool:
        cfg = self._build_config()
        try:
            result = parse_accounts(self._wiz._raw_rows, **cfg)
        except Exception as e:
            QMessageBox.critical(self, "Parse Error", str(e))
            return False
        if not result.accounts:
            QMessageBox.warning(
                self, "No Accounts Found",
                "No account rows were found with the current settings.\n"
                "Check that the header row and column assignments are correct.",
            )
            return False
        self._wiz._parse_result = result
        self._wiz._col_config = cfg
        return True

    def _build_config(self) -> dict:
        def idx(combo: QComboBox) -> int | None:
            text = combo.currentText()
            if text == _NO_COL:
                return None
            # "B: Account Name" → extract the letter before ":"
            letter = text.split(":")[0].strip()
            return _col_letter_to_idx(letter)

        cfg: dict = {
            "header_row": self._header_spin.value() - 1,
            "name_col":   idx(self._name_combo),
            "number_col": idx(self._number_combo),
        }
        if self._mode_single.isChecked():
            cfg["balance_col"] = idx(self._balance_combo)
        else:
            cfg["debit_col"]  = idx(self._debit_combo)
            cfg["credit_col"] = idx(self._credit_combo)
        return cfg


# ---------------------------------------------------------------------------
# Page 2 — Confirm
# ---------------------------------------------------------------------------

class _ConfirmPage(QWizardPage):
    def __init__(self, wizard: TBImportWizard):
        super().__init__(wizard)
        self._wiz = wizard
        self.setTitle("Confirm Import")
        self.setSubTitle("Review the results, then click Import to write accounts to the workup file.")
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        self._lbl = QLabel()
        self._lbl.setWordWrap(True)
        f = QFont()
        f.setPointSize(11)
        self._lbl.setFont(f)
        layout.addWidget(self._lbl)
        layout.addStretch()

    def initializePage(self):
        r = self._wiz._parse_result
        if r is None:
            return
        diff = round(r.total_debits + r.total_credits, 2)
        if r.is_balanced:
            bal_html = "<span style='color:green'>&#10003; In balance</span>"
        else:
            bal_html = f"<span style='color:red'>&#10007; Out of balance by {diff:,.2f}</span>"

        self._lbl.setText(
            f"<b>{len(r.accounts)}</b> accounts ready to import.<br>"
            f"Rows skipped (blank / non-data): {r.skipped_rows}<br><br>"
            f"Total debits &nbsp;: <b>{r.total_debits:>14,.2f}</b><br>"
            f"Total credits: <b>{r.total_credits:>14,.2f}</b><br><br>"
            f"{bal_html}"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _col_letter(idx: int) -> str:
    result = ""
    n = idx + 1
    while n:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result


def _col_letter_to_idx(letter: str) -> int:
    result = 0
    for ch in letter.upper():
        result = result * 26 + (ord(ch) - ord("A") + 1)
    return result - 1


def _guess_name_col(rows: list[list[Any]], n_cols: int) -> int:
    best, best_score = -1, 0
    for c in range(n_cols):
        score = sum(
            1 for row in rows[:15]
            if c < len(row) and isinstance(row[c], str) and len(row[c].strip()) > 2
        )
        if score > best_score:
            best_score, best = score, c
    return best


def _guess_balance_col(
    rows: list[list[Any]], n_cols: int, skip_col: int, header_row: int
) -> int:
    from atbworkup.importer.tb_parser import _try_parse_amount
    for c in range(n_cols):
        if c == skip_col:
            continue
        numeric = sum(
            1 for row in rows[header_row + 1: header_row + 15]
            if c < len(row) and row[c] is not None
            and _try_parse_amount(str(row[c]))[1]
        )
        if numeric >= 3:
            return c
    return -1
