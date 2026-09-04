"""
Journal Entry panel — sits at the bottom of WorkupWindow.

Left:  list of all JEs for this binder (click to load in editor).
Right: line-item editor for the selected/new JE.

Keyboard UX:
  - Account field: editable, searches by number or name, Enter/Tab applies
  - Tab advances Account → DR → CR → Memo
  - Tab on last row's Memo creates a new blank line automatically
  - Scroll wheel only changes account combo when it has keyboard focus

DR amounts entered as positive, CR as negative (sign convention throughout).
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QComboBox,
    QSplitter, QHeaderView, QAbstractItemView, QCompleter,
    QFrame, QDialog, QDialogButtonBox, QFormLayout, QMessageBox,
)
from PySide6.QtCore import Qt, Signal, QStringListModel, QSortFilterProxyModel
from PySide6.QtWidgets import QMenu
from PySide6.QtGui import QColor, QFont, QKeyEvent

from atbworkup.db.connection import db_connection
from atbworkup.models.journal_entries import (
    create_entry, get_entries, get_entry, get_lines,
    save_lines, delete_entry, entry_balance, next_entry_number,
    update_entry, signoff_entry, remove_signoff,
)
from atbworkup.models.activity import log_activity

# ── Constants ────────────────────────────────────────────────────────────────
_ENTRY_TYPES = ["AJE", "RJE", "FTJE"]

_COL_ACCT = 0
_COL_DR   = 1
_COL_CR   = 2
_COL_MEMO = 3
_COL_DEL  = 4

_LIST_COLS   = ["#", "Type", "Description", "", "R"]
_EDITOR_COLS = ["Account", "DR", "CR", "Memo", ""]

_COLLAPSED_HEIGHT = 32   # just the header bar


# ── Account combo ─────────────────────────────────────────────────────────────

class _AccountCombo(QComboBox):
    """
    Editable combo for account selection.
    - Scroll wheel ignored unless the widget has keyboard focus.
    - Completer searches both account number and name (case-insensitive).
    - Tab/Enter apply the current completion and advance focus.
    - If Tab/Enter pressed with unrecognised text, emits account_not_found(text).
    """

    account_not_found = Signal(str)   # emits typed text when no match on Tab/Enter

    def __init__(self, accounts: list[dict], parent=None):
        super().__init__(parent)
        self._accounts = accounts          # [{account_id, account_number, account_name}]
        self._id_by_display: dict[str, str] = {}

        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.setFocusPolicy(Qt.StrongFocus)
        self.lineEdit().setPlaceholderText("Account # or name…")

        # Build display strings and id map
        displays = []
        self.addItem("", None)
        for a in accounts:
            num  = (a.get("account_number") or "").strip()
            name = a["account_name"].strip()
            display = f"{num}  {name}" if num else name
            displays.append(display)
            self._id_by_display[display] = a["account_id"]
            self.addItem(display, a["account_id"])

        # Completer — searches anywhere in the string
        completer = QCompleter(displays, self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        self.setCompleter(completer)

        # Apply completion on activation (click or Enter in popup)
        completer.activated.connect(self._on_completion_chosen)

        # Tab inside the popup should accept the highlighted row and advance focus.
        # The popup is created lazily — install the filter after first show.
        completer.popup().installEventFilter(self)

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        popup = self.completer().popup() if self.completer() else None
        if popup and obj is popup and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Tab:
                idx = popup.currentIndex()
                if idx.isValid():
                    chosen = self.completer().completionModel().data(idx)
                    self._on_completion_chosen(chosen)
                popup.hide()
                self.focusNextChild()
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key_Tab, Qt.Key_Return, Qt.Key_Enter):
            text = self.currentText().strip()
            if text and self.current_account_id() is None:
                self.account_not_found.emit(text)
                event.accept()
                return
            # Resolve partial input (e.g. just "1000") to full "1000  Cash" display
            if text:
                aid = self.current_account_id()
                if aid:
                    for a in self._accounts:
                        if a["account_id"] == aid:
                            num  = (a.get("account_number") or "").strip()
                            name = a["account_name"].strip()
                            full = f"{num}  {name}" if num else name
                            if self.currentText() != full:
                                self._on_completion_chosen(full)
                            break
        super().keyPressEvent(event)

    def wheelEvent(self, event):
        # Only scroll through options when this widget has keyboard focus
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()

    def _on_completion_chosen(self, text: str):
        idx = self.findText(text)
        if idx >= 0:
            self.setCurrentIndex(idx)
        # Belt-and-braces: setCurrentIndex should already sync the line
        # edit's displayed text, but a completer selection made by clicking
        # a popup suggestion with the mouse (as opposed to keyboard Tab/
        # Enter, which is separately handled in keyPressEvent) was observed
        # to sometimes leave stray or duplicated characters in the line
        # edit instead of the clean selected text. Force it explicitly so
        # the field can't end up in an inconsistent state either way.
        self.lineEdit().setText(text)

    def current_account_id(self) -> str | None:
        """Return the account_id for the currently displayed text, or None."""
        text = self.currentText().strip()
        # exact match by display string
        if text in self._id_by_display:
            return self._id_by_display[text]
        # match by account_id stored in item data
        aid = self.currentData()
        if aid:
            return aid
        # try prefix match on account number
        for a in self._accounts:
            num = (a.get("account_number") or "").strip()
            if num and text.startswith(num):
                return a["account_id"]
        return None

    def set_account(self, account_id: str):
        idx = self.findData(account_id)
        if idx >= 0:
            self.setCurrentIndex(idx)

    def refresh_accounts(self, accounts: list[dict]):
        """Rebuild the combo from a fresh account list (call after external account creation)."""
        self._accounts = accounts
        self._id_by_display = {}
        self.clear()
        self.addItem("", None)
        displays = []
        for a in accounts:
            num  = (a.get("account_number") or "").strip()
            name = a["account_name"].strip()
            display = f"{num}  {name}" if num else name
            displays.append(display)
            self._id_by_display[display] = a["account_id"]
            self.addItem(display, a["account_id"])
        from PySide6.QtCore import QStringListModel
        self.completer().setModel(QStringListModel(displays, self))

    def add_new_account(self, account: dict):
        """Append a freshly-created account to this combo's UI without touching
        the shared accounts list — JEPanel updates that list exactly once."""
        num  = (account.get("account_number") or "").strip()
        name = account["account_name"].strip()
        display = f"{num}  {name}" if num else name
        self._id_by_display[display] = account["account_id"]
        # Do NOT append to self._accounts here; it's a shared reference and
        # JEPanel already called self._accounts.append() before calling this.
        self.addItem(display, account["account_id"])
        displays = [self.itemText(i) for i in range(1, self.count())]
        from PySide6.QtCore import QStringListModel
        self.completer().setModel(QStringListModel(displays, self))


# ── Account creation dialog ───────────────────────────────────────────────────

_ACCOUNT_TYPES = ["Asset", "Liability", "Equity", "Revenue", "Expense"]
_NORMAL_BALANCE = {
    "Asset":     "Debit",
    "Expense":   "Debit",
    "Liability": "Credit",
    "Equity":    "Credit",
    "Revenue":   "Credit",
}


class _CreateAccountDialog(QDialog):
    """Small modal for creating a new account on the fly."""

    def __init__(self, prefill_text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create Account")
        self.setMinimumWidth(360)
        self._result: dict | None = None
        self._build_ui(prefill_text)

    def created_account_data(self) -> dict | None:
        return self._result

    def _build_ui(self, prefill_text: str):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        layout.addWidget(QLabel("Account not found. Create it now?"))

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)

        # Pre-fill: if text looks like a number/code, put in Number; else Name
        looks_like_num = prefill_text.replace("-", "").replace(".", "").isdigit()
        self._num_edit = QLineEdit(prefill_text if looks_like_num else "")
        self._num_edit.setPlaceholderText("e.g. 1200")
        form.addRow("Account #:", self._num_edit)

        self._name_edit = QLineEdit("" if looks_like_num else prefill_text)
        self._name_edit.setPlaceholderText("e.g. Accounts Receivable")
        form.addRow("Name:", self._name_edit)

        self._type_combo = QComboBox()
        self._type_combo.addItems(_ACCOUNT_TYPES)
        self._type_combo.currentTextChanged.connect(self._on_type_changed)
        form.addRow("Type:", self._type_combo)

        self._nb_label = QLabel(_NORMAL_BALANCE["Asset"])
        self._nb_label.setStyleSheet("color: #555555; font-style: italic;")
        form.addRow("Normal Balance:", self._nb_label)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._name_edit.setFocus()

    def _on_type_changed(self, t: str):
        self._nb_label.setText(_NORMAL_BALANCE.get(t, "Debit"))

    def _on_ok(self):
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Required", "Account name is required.")
            return
        acct_type = self._type_combo.currentText()
        self._result = {
            "account_number": self._num_edit.text().strip() or None,
            "account_name":   name,
            "account_type":   acct_type,
            "normal_balance": _NORMAL_BALANCE[acct_type],
        }
        self.accept()


# ── Memo field with tab-to-new-line ───────────────────────────────────────────

class _MemoEdit(QLineEdit):
    # Emits on plain forward-Tab; the panel decides whether to add a new row
    # or move focus to the next existing row's account combo. Handling both
    # cases here (rather than leaning on Qt's default cross-widget tab chain)
    # avoids relying on focusNextPrevChild() correctly threading through cell
    # widgets embedded in a QTableWidget, which is unreliable in practice.
    tab_pressed = Signal()

    def focusNextPrevChild(self, next: bool) -> bool:
        # Plain Tab (no modifiers) is resolved by QWidget::event() via
        # focusNextPrevChild() BEFORE keyPressEvent() is ever called, so the
        # interception has to live here, not in keyPressEvent.
        if next:
            self.tab_pressed.emit()
            return True
        return super().focusNextPrevChild(next)


# ── Amount field ──────────────────────────────────────────────────────────────

class _AmountEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.setPlaceholderText("0.00")

    def wheelEvent(self, event):
        event.ignore()


# ── Main panel ────────────────────────────────────────────────────────────────

class JEPanel(QWidget):
    """Bottom-docked journal entry panel."""

    entries_changed = Signal()
    note_requested  = Signal(str, str)   # (aje_id, display_label)

    def __init__(self, path: str | Path, job_id: str, performed_by: str,
                 parent=None):
        super().__init__(parent)
        self._path          = Path(path)
        self._job_id        = job_id
        self._performed_by  = performed_by
        self._current_aje_id: str | None = None
        self._accounts: list[dict] = []

        self._build_ui()
        self._load_accounts()
        self.reload_list()

    # ── Build ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header bar ────────────────────────────────────────────────────
        # NOTE: title/pop-out/hide controls live in the wrapper header built by
        # WorkupWindow._rebuild_je_panel — this bar only holds the quick-add buttons.
        hdr = QWidget()
        hdr.setStyleSheet("background: #1A2B4C;")
        hdr.setFixedHeight(_COLLAPSED_HEIGHT)
        hdr_layout = QHBoxLayout(hdr)
        hdr_layout.setContentsMargins(10, 0, 8, 0)
        hdr_layout.addStretch()

        for et in _ENTRY_TYPES:
            btn = QPushButton(f"+ {et}")
            btn.setFixedHeight(22)
            btn.setStyleSheet(
                "background: #FFFFFF; color: #1A2B4C; font-weight: bold; "
                "font-size: 11px; border-radius: 2px; padding: 0 8px;"
            )
            btn.clicked.connect(lambda _=False, t=et: self.new_entry(t))
            hdr_layout.addWidget(btn)

        self._quick_add_hdr = hdr
        root.addWidget(hdr)

        # ── Body (hidden when collapsed) ───────────────────────────────────
        self._body = QWidget()
        body_layout = QVBoxLayout(self._body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(4)
        splitter.setChildrenCollapsible(False)

        # Left: JE list
        self._list = QTableWidget(0, 5)
        self._list.setHorizontalHeaderLabels(_LIST_COLS)
        self._list.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._list.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._list.setAlternatingRowColors(True)
        self._list.verticalHeader().setVisible(False)
        self._list.setShowGrid(False)
        lhdr = self._list.horizontalHeader()
        lhdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        lhdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        lhdr.setSectionResizeMode(2, QHeaderView.Stretch)
        lhdr.setSectionResizeMode(3, QHeaderView.Fixed)
        lhdr.setSectionResizeMode(4, QHeaderView.Fixed)
        self._list.setColumnWidth(3, 24)
        self._list.setColumnWidth(4, 24)
        self._list.setStyleSheet(_table_style())
        self._list.currentCellChanged.connect(self._on_list_select)
        self._list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_list_context_menu)
        splitter.addWidget(self._list)

        # Right: editor
        editor_widget = QWidget()
        editor_layout = QVBoxLayout(editor_widget)
        editor_layout.setContentsMargins(8, 6, 8, 6)
        editor_layout.setSpacing(6)

        meta_row = QHBoxLayout()
        self._type_combo = QComboBox()
        self._type_combo.addItems(_ENTRY_TYPES)
        self._type_combo.setFixedWidth(80)
        self._type_combo.setFocusPolicy(Qt.StrongFocus)
        self._type_combo.wheelEvent = lambda e: e.ignore()
        self._type_combo.currentTextChanged.connect(self._on_type_changed)

        self._number_lbl = QLabel("—")
        self._number_lbl.setStyleSheet("color: #888888; font-size: 12px;")
        self._number_lbl.setFixedWidth(100)

        self._desc = QLineEdit()
        self._desc.setPlaceholderText("Description…")
        self._desc.textChanged.connect(self._update_list_description)

        meta_row.addWidget(QLabel("Type:"))
        meta_row.addWidget(self._type_combo)
        meta_row.addWidget(self._number_lbl)
        meta_row.addWidget(self._desc, 1)
        editor_layout.addLayout(meta_row)

        self._lines_table = QTableWidget(0, 5)
        self._lines_table.setHorizontalHeaderLabels(_EDITOR_COLS)
        self._lines_table.verticalHeader().setVisible(False)
        self._lines_table.setSelectionMode(QAbstractItemView.NoSelection)
        self._lines_table.setFocusPolicy(Qt.NoFocus)
        self._lines_table.setStyleSheet(_table_style())
        ehdr = self._lines_table.horizontalHeader()
        ehdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (_COL_DR, _COL_CR):
            ehdr.setSectionResizeMode(c, QHeaderView.Fixed)
            self._lines_table.setColumnWidth(c, 110)
        ehdr.setSectionResizeMode(_COL_MEMO, QHeaderView.Stretch)
        ehdr.setSectionResizeMode(_COL_DEL, QHeaderView.Fixed)
        self._lines_table.setColumnWidth(_COL_DEL, 28)
        editor_layout.addWidget(self._lines_table, 1)

        bottom_row = QHBoxLayout()
        add_line_btn = QPushButton("+ Add Line")
        add_line_btn.setFixedWidth(100)
        add_line_btn.setStyleSheet(
            "background: #E5E5E5; color: #000000; font-weight: normal;"
        )
        add_line_btn.clicked.connect(self._add_blank_line)

        new_acct_btn = QPushButton("+ New Account…")
        new_acct_btn.setFixedWidth(130)
        new_acct_btn.setStyleSheet(
            "QPushButton { background: #E5E5E5; color: #1A2B4C; font-weight: normal; "
            "border: 1px solid #AAAAAA; border-radius: 2px; }"
            "QPushButton:hover { background: #D0DCEE; }"
        )
        new_acct_btn.setToolTip(
            "Create a new account and add it to the current line.\n"
            "You can also type an unknown account name and press Tab."
        )
        new_acct_btn.clicked.connect(self._on_new_account_btn)

        self._balance_lbl = QLabel("Balance: —")
        self._balance_lbl.setStyleSheet("font-weight: bold; font-size: 12px;")
        bottom_row.addWidget(add_line_btn)
        bottom_row.addWidget(new_acct_btn)
        bottom_row.addStretch()
        bottom_row.addWidget(self._balance_lbl)
        editor_layout.addLayout(bottom_row)

        action_row = QHBoxLayout()
        self._delete_btn = QPushButton("Delete Entry")
        self._delete_btn.setStyleSheet(
            "background: #7B1A1A; color: #FFFFFF; font-weight: bold;"
        )
        self._delete_btn.setEnabled(False)
        self._delete_btn.clicked.connect(self._do_delete)

        self._save_btn = QPushButton("Save")
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._do_save)

        self._signoff_btn = QPushButton("Reviewer Sign Off")
        self._signoff_btn.setEnabled(False)
        self._signoff_btn.clicked.connect(self._do_signoff)
        self._signoff_btn.setStyleSheet(
            "background: #6B2D8B; color: #FFFFFF; font-weight: bold; padding: 4px 12px;"
        )

        action_row.addWidget(self._delete_btn)
        action_row.addStretch()
        action_row.addWidget(self._signoff_btn)
        action_row.addWidget(self._save_btn)
        editor_layout.addLayout(action_row)

        splitter.addWidget(editor_widget)
        splitter.setSizes([280, 620])

        body_layout.addWidget(splitter, 1)
        root.addWidget(self._body, 1)

        self._set_editor_enabled(False)

    # ── Collapse ──────────────────────────────────────────────────────────

    # ── Accounts ──────────────────────────────────────────────────────────

    def _load_accounts(self):
        with db_connection(self._path) as conn:
            rows = conn.execute(
                """SELECT account_id, account_number, account_name
                   FROM accounts WHERE job_id = ?
                   ORDER BY account_number, account_name""",
                (self._job_id,),
            ).fetchall()
        self._accounts = [dict(r) for r in rows]

    def _maybe_autofill_description(self, combo: "_AccountCombo"):
        """If the JE description is still blank, fill it with the selected account name."""
        if self._desc.text().strip():
            return
        aid = combo.current_account_id()
        if not aid:
            return
        for a in self._accounts:
            if a["account_id"] == aid:
                self._desc.setText(a["account_name"])
                return

    def _on_account_not_found(self, combo: "_AccountCombo", typed_text: str):
        """Called when the user tabs/enters an unrecognised account name."""
        dlg = _CreateAccountDialog(typed_text, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        data = dlg.created_account_data()
        if not data:
            return

        from atbworkup.models.accounts import create_account
        from atbworkup.models.activity import log_activity
        try:
            with db_connection(self._path) as conn:
                account_id = create_account(
                    conn, self._job_id,
                    account_number = data["account_number"] or "",
                    account_name   = data["account_name"],
                    account_type   = data["account_type"],
                    normal_balance = data["normal_balance"],
                )
                log_activity(
                    conn,
                    job_id       = self._job_id,
                    event_type   = "created_account",
                    entity_type  = "account",
                    entity_id    = account_id,
                    description  = f"Created account: {data['account_name']}",
                    performed_by = self._performed_by,
                )
        except ValueError as exc:
            QMessageBox.warning(self, "Duplicate Account Number", str(exc))
            return

        new_acct = {
            "account_id":     account_id,
            "account_number": data["account_number"] or "",
            "account_name":   data["account_name"],
        }
        # Update the shared list once here; add_new_account only updates combo UI.
        self._accounts.append(new_acct)
        for r in range(self._lines_table.rowCount()):
            w = self._lines_table.cellWidget(r, _COL_ACCT)
            if isinstance(w, _AccountCombo) and w is not combo:
                w.add_new_account(new_acct)
        # Add to the triggering combo and select it
        combo.add_new_account(new_acct)
        combo.set_account(account_id)
        combo.setFocus()

    def _on_new_account_btn(self):
        """Explicit 'New Account…' button — opens create dialog and targets
        the first empty account combo on the current entry."""
        dlg = _CreateAccountDialog("", parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        data = dlg.created_account_data()
        if not data:
            return

        from atbworkup.models.accounts import create_account
        try:
            with db_connection(self._path) as conn:
                account_id = create_account(
                    conn, self._job_id,
                    account_number = data["account_number"] or "",
                    account_name   = data["account_name"],
                    account_type   = data["account_type"],
                    normal_balance = data["normal_balance"],
                )
                log_activity(
                    conn,
                    job_id       = self._job_id,
                    event_type   = "created_account",
                    entity_type  = "account",
                    entity_id    = account_id,
                    description  = f"Created account: {data['account_name']}",
                    performed_by = self._performed_by,
                )
        except ValueError as exc:
            QMessageBox.warning(self, "Duplicate Account Number", str(exc))
            return

        new_acct = {
            "account_id":     account_id,
            "account_number": data["account_number"] or "",
            "account_name":   data["account_name"],
        }
        self._accounts.append(new_acct)

        # Inject into all combos and find the first empty one to select it in
        first_empty_combo: "_AccountCombo | None" = None
        for r in range(self._lines_table.rowCount()):
            w = self._lines_table.cellWidget(r, _COL_ACCT)
            if isinstance(w, _AccountCombo):
                w.add_new_account(new_acct)
                if first_empty_combo is None and w.current_account_id() is None:
                    first_empty_combo = w

        if first_empty_combo is not None:
            first_empty_combo.set_account(account_id)
            first_empty_combo.setFocus()
        else:
            # All lines already have accounts — add a new line with it selected
            self._append_line_row(account_id=account_id)

    # ── JE list ───────────────────────────────────────────────────────────

    def reload_list(self):
        self._list.blockSignals(True)
        self._list.setRowCount(0)
        with db_connection(self._path) as conn:
            entries = get_entries(conn, self._job_id)
        for e in entries:
            r = self._list.rowCount()
            self._list.insertRow(r)
            self._list.setItem(r, 0, _ro_item(e["entry_number"]))
            self._list.setItem(r, 1, _ro_item(e["entry_type"]))
            self._list.setItem(r, 2, _ro_item(e["description"]))
            bal_item = _ro_item("✓" if e["is_balanced"] else "✗")
            bal_item.setForeground(
                QColor("#2e7d32") if e["is_balanced"] else QColor("#C62828")
            )
            bal_item.setTextAlignment(Qt.AlignCenter)
            self._list.setItem(r, 3, bal_item)

            signed = bool(e.get("reviewer_signoff_by"))
            so_item = _ro_item("✓" if signed else "")
            so_item.setForeground(QColor("#6B2D8B"))
            so_item.setTextAlignment(Qt.AlignCenter)
            self._list.setItem(r, 4, so_item)

            self._list.item(r, 0).setData(Qt.UserRole, e["aje_id"])
        self._list.resizeRowsToContents()
        self._list.blockSignals(False)

    def _update_list_description(self, text: str):
        """Reflect description edits in the list immediately (before save)."""
        if not self._current_aje_id:
            return
        for r in range(self._list.rowCount()):
            item = self._list.item(r, 0)
            if item and item.data(Qt.UserRole) == self._current_aje_id:
                desc_item = self._list.item(r, 2)
                if desc_item:
                    desc_item.setText(text)
                break

    def _on_list_context_menu(self, pos):
        row = self._list.rowAt(pos.y())
        if row < 0:
            return
        item = self._list.item(row, 0)
        if not item:
            return
        aje_id = item.data(Qt.UserRole)
        number = item.text()
        desc   = (self._list.item(row, 2) or item).text()
        label  = f"{number} — {desc}"

        menu = QMenu(self)
        note_action = menu.addAction("Add Note…")
        action = menu.exec(self._list.viewport().mapToGlobal(pos))
        if action == note_action:
            self.note_requested.emit(aje_id, label)

    def _on_list_select(self, row: int, *_):
        if row < 0:
            return
        item = self._list.item(row, 0)
        if item:
            self._load_entry(item.data(Qt.UserRole))

    def _load_entry(self, aje_id: str):
        self._current_aje_id = aje_id
        with db_connection(self._path) as conn:
            entry = get_entry(conn, aje_id)
            lines = get_lines(conn, aje_id)
        if not entry:
            return
        self._type_combo.blockSignals(True)
        self._type_combo.setCurrentText(entry["entry_type"])
        self._type_combo.blockSignals(False)
        self._number_lbl.setText(entry["entry_number"])
        self._desc.setText(entry["description"])
        self._lines_table.setRowCount(0)
        for ln in lines:
            self._append_line_row(
                account_id=ln["account_id"],
                amount=ln["amount"],
                memo=ln.get("memo") or "",
            )
        self._add_blank_line()
        self._update_balance()
        self._set_editor_enabled(True)
        self._delete_btn.setEnabled(True)
        self._update_signoff_btn(entry)

    # ── Editor rows ───────────────────────────────────────────────────────

    def _append_line_row(self, account_id: str | None = None,
                         amount: float = 0.0, memo: str = ""):
        r = self._lines_table.rowCount()
        self._lines_table.insertRow(r)
        self._lines_table.setRowHeight(r, 28)

        # Account combo
        combo = _AccountCombo(self._accounts)
        if account_id:
            combo.set_account(account_id)
        combo.currentIndexChanged.connect(self._update_balance)
        combo.currentIndexChanged.connect(
            lambda _, c=combo: self._maybe_autofill_description(c)
        )
        combo.account_not_found.connect(
            lambda text, c=combo: self._on_account_not_found(c, text)
        )
        self._lines_table.setCellWidget(r, _COL_ACCT, combo)

        # DR / CR
        dr = _AmountEdit()
        cr = _AmountEdit()
        if amount > 0:
            dr.setText(f"{amount:.2f}")
        elif amount < 0:
            cr.setText(f"{abs(amount):.2f}")
        # editingFinished (not textChanged) — recomputing the balance on
        # every keystroke means it changes mid-typing while "plugging" an
        # entry, forcing the preparer to write down the out-of-balance
        # amount before it moves. Waiting until the cell is actually left
        # (Tab/Enter/click-away) gives one stable read after each amount.
        dr.editingFinished.connect(self._update_balance)
        cr.editingFinished.connect(self._update_balance)
        self._lines_table.setCellWidget(r, _COL_DR, dr)
        self._lines_table.setCellWidget(r, _COL_CR, cr)

        # Memo — Tab either advances to the next row's account combo, or,
        # if this is the last row, adds a new blank line and focuses it.
        memo_edit = _MemoEdit()
        memo_edit.setText(memo)
        memo_edit._row = r
        memo_edit.tab_pressed.connect(lambda w=memo_edit: self._on_memo_tab(w))
        self._lines_table.setCellWidget(r, _COL_MEMO, memo_edit)

        # Delete button — mouse-only; excluded from Tab order so it doesn't
        # break the combo -> dr -> cr -> memo -> next-row-combo keyboard flow.
        del_btn = QPushButton("×")
        del_btn.setFixedSize(24, 24)
        del_btn.setFocusPolicy(Qt.NoFocus)
        del_btn.setStyleSheet(
            "background: transparent; color: #C62828; "
            "font-weight: bold; border: none;"
        )
        del_btn.clicked.connect(lambda _=False, row=r: self._remove_line_row(row))
        self._lines_table.setCellWidget(r, _COL_DEL, del_btn)

        # combo → dr → cr within a row still uses Qt's default tab chain
        # (that part is reliable); memo's Tab is handled explicitly above
        # since cross-row navigation via the default chain is not.
        QWidget.setTabOrder(combo, dr)
        QWidget.setTabOrder(dr, cr)
        QWidget.setTabOrder(cr, memo_edit)

    def _on_memo_tab(self, memo_widget: "_MemoEdit"):
        row = memo_widget._row
        if row == self._lines_table.rowCount() - 1:
            self._add_blank_line()
        next_combo = self._lines_table.cellWidget(row + 1, _COL_ACCT)
        if next_combo:
            next_combo.setFocus()
            next_combo.lineEdit().selectAll()

    def _add_blank_line(self):
        self._append_line_row()

    def _remove_line_row(self, row: int):
        self._lines_table.removeRow(row)
        # Rewire delete button + memo row indices (they shift after removal)
        for r in range(self._lines_table.rowCount()):
            btn = self._lines_table.cellWidget(r, _COL_DEL)
            if btn:
                try:
                    btn.clicked.disconnect()
                except RuntimeError:
                    pass
                btn.clicked.connect(lambda _=False, rr=r: self._remove_line_row(rr))
            memo = self._lines_table.cellWidget(r, _COL_MEMO)
            if isinstance(memo, _MemoEdit):
                memo._row = r
        self._update_balance()

    def _collect_lines(self) -> list[dict]:
        lines = []
        for r in range(self._lines_table.rowCount()):
            combo  = self._lines_table.cellWidget(r, _COL_ACCT)
            dr_w   = self._lines_table.cellWidget(r, _COL_DR)
            cr_w   = self._lines_table.cellWidget(r, _COL_CR)
            memo_w = self._lines_table.cellWidget(r, _COL_MEMO)
            if not isinstance(combo, _AccountCombo):
                continue
            account_id = combo.current_account_id()
            if not account_id:
                continue
            dr = _parse_amount(dr_w.text() if dr_w else "")
            cr = _parse_amount(cr_w.text() if cr_w else "")
            amount = round(dr - cr, 2)
            memo = memo_w.text() if memo_w else ""
            lines.append({"account_id": account_id, "amount": amount, "memo": memo})
        return lines

    def _update_balance(self, *_):
        lines = self._collect_lines()
        total = entry_balance(lines)
        balanced = abs(total) < 0.005
        if balanced:
            self._balance_lbl.setText("Balance: —  ✓")
            self._balance_lbl.setStyleSheet("font-weight: bold; color: #2e7d32;")
        else:
            self._balance_lbl.setText(f"Balance: {total:+,.2f}  ✗")
            self._balance_lbl.setStyleSheet("font-weight: bold; color: #C62828;")
        self._save_btn.setEnabled(balanced and bool(lines))

    def _update_signoff_btn(self, entry: dict):
        signed = bool(entry.get("reviewer_signoff_by"))
        self._signoff_btn.setEnabled(True)
        if signed:
            self._signoff_btn.setText("Remove Sign Off")
            self._signoff_btn.setStyleSheet(
                "background: #E5E5E5; color: #6B2D8B; font-weight: bold; padding: 4px 12px;"
            )
        else:
            self._signoff_btn.setText("Reviewer Sign Off")
            self._signoff_btn.setStyleSheet(
                "background: #6B2D8B; color: #FFFFFF; font-weight: bold; padding: 4px 12px;"
            )

    def _do_signoff(self):
        if not self._current_aje_id:
            return
        with db_connection(self._path) as conn:
            entry = get_entry(conn, self._current_aje_id)
            if entry and entry.get("reviewer_signoff_by"):
                remove_signoff(conn, self._current_aje_id)
            else:
                signoff_entry(conn, self._current_aje_id, self._performed_by)
            entry = get_entry(conn, self._current_aje_id)
        self._update_signoff_btn(entry)
        self.reload_list()
        self._select_entry_in_list(self._current_aje_id)

    def _set_editor_enabled(self, enabled: bool):
        self._type_combo.setEnabled(enabled)
        self._desc.setEnabled(enabled)
        self._lines_table.setEnabled(enabled)
        self._save_btn.setEnabled(False)
        if not enabled:
            self._signoff_btn.setEnabled(False)

    # ── New entry ─────────────────────────────────────────────────────────

    def new_entry(self, entry_type: str, prefill_account_id: str | None = None):
        self._current_aje_id = None
        self._type_combo.blockSignals(True)
        self._type_combo.setCurrentText(entry_type)
        self._type_combo.blockSignals(False)
        with db_connection(self._path) as conn:
            number = next_entry_number(conn, self._job_id, entry_type)
        self._number_lbl.setText(f"{number}  (unsaved)")
        self._desc.clear()
        self._lines_table.setRowCount(0)
        if prefill_account_id:
            self._append_line_row(account_id=prefill_account_id)
        self._add_blank_line()
        self._update_balance()
        self._set_editor_enabled(True)
        self._delete_btn.setEnabled(False)
        self._signoff_btn.setEnabled(False)
        self._list.clearSelection()

        # Focus description first, then user tabs into lines
        self._desc.setFocus()

    def _on_type_changed(self, entry_type: str):
        if self._current_aje_id:
            return
        with db_connection(self._path) as conn:
            number = next_entry_number(conn, self._job_id, entry_type)
        self._number_lbl.setText(f"{number}  (unsaved)")

    # ── Save / Delete ─────────────────────────────────────────────────────

    def _do_save(self):
        lines = self._collect_lines()
        if not lines:
            return
        entry_type  = self._type_combo.currentText()
        description = self._desc.text().strip() or entry_type

        with db_connection(self._path) as conn:
            if self._current_aje_id:
                update_entry(conn, self._current_aje_id, description=description)
                save_lines(conn, self._current_aje_id, lines)
                event = "changed_aje"
            else:
                entry = create_entry(
                    conn,
                    job_id=self._job_id,
                    entry_type=entry_type,
                    description=description,
                    originated_by=self._performed_by,
                    status="Open",
                )
                self._current_aje_id = entry["aje_id"]
                save_lines(conn, self._current_aje_id, lines)
                event = "added_aje"
            log_activity(
                conn,
                job_id=self._job_id,
                event_type=event,
                description=f"{event.replace('_', ' ').title()}: {description}",
                performed_by=self._performed_by,
            )

        self.reload_list()
        self._select_entry_in_list(self._current_aje_id)
        self.entries_changed.emit()

    def _do_delete(self):
        if not self._current_aje_id:
            return
        with db_connection(self._path) as conn:
            delete_entry(conn, self._current_aje_id)
            log_activity(
                conn,
                job_id=self._job_id,
                event_type="deleted_aje",
                description="Deleted journal entry",
                performed_by=self._performed_by,
            )
        self._current_aje_id = None
        self._lines_table.setRowCount(0)
        self._desc.clear()
        self._number_lbl.setText("—")
        self._set_editor_enabled(False)
        self._delete_btn.setEnabled(False)
        self.reload_list()
        self.entries_changed.emit()

    def _select_entry_in_list(self, aje_id: str):
        for r in range(self._list.rowCount()):
            item = self._list.item(r, 0)
            if item and item.data(Qt.UserRole) == aje_id:
                self._list.selectRow(r)
                break

    # ── Public API ────────────────────────────────────────────────────────

    def set_body_visible(self, visible: bool):
        """Hide/show the quick-add bar and entry list+editor (used when the
        outer wrapper header collapses this panel to save vertical space)."""
        self._quick_add_hdr.setVisible(visible)
        self._body.setVisible(visible)

    def reload_accounts(self):
        """Refresh the account list so newly created accounts are immediately selectable."""
        self._load_accounts()
        for w in self.findChildren(_AccountCombo):
            current_id = w.current_account_id()
            w.refresh_accounts(self._accounts)
            if current_id:
                w.set_account(current_id)

    def open_for_account(self, account_id: str, entry_type: str):
        self._load_accounts()
        self.new_entry(entry_type, prefill_account_id=account_id)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ro_item(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
    return item


def _parse_amount(text: str) -> float:
    text = text.strip().replace(",", "")
    try:
        return float(text)
    except ValueError:
        return 0.0


def _table_style() -> str:
    return """
        QTableWidget {
            font-family: "Segoe UI";
            font-size: 12px;
            background: #FFFFFF;
            color: #000000;
            alternate-background-color: #F5F5F5;
            gridline-color: #E5E5E5;
            border: 1px solid #E5E5E5;
        }
        QTableWidget::item:selected {
            background: #1A2B4C;
            color: #FFFFFF;
        }
        QHeaderView::section {
            background: #1A2B4C;
            color: #FFFFFF;
            font-family: "Segoe UI";
            font-size: 11px;
            font-weight: bold;
            letter-spacing: 1px;
            padding: 4px 6px;
            border: 1px solid #0f1d33;
        }
    """
