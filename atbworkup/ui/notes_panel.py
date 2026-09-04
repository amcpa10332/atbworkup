"""
Notes panel — QDockWidget showing preparer, reviewer, and delivery notes.

- Open / All filter toggle
- Scrollable note cards with role-appropriate action buttons
- Reviewer notes: blue left border, "R" badge
- Delivery notes: gold left border, "D" badge — client items, don't block finalization
- Preparer notes: red left border
- Click a card to navigate to the linked account or JE
- Emits notes_changed after any write
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QFrame,
    QButtonGroup, QDialog, QComboBox, QTextEdit, QDialogButtonBox,
)
from PySide6.QtCore import Qt, Signal

from atbworkup.db.connection import db_connection
from atbworkup.models.notes import (
    get_notes, clear_note, resolve_note, open_note_count, create_note,
)
from atbworkup.constants import NOTE_TYPE_COLORS

_HEADER_BG  = "#1A2B4C"
_C_PREP     = NOTE_TYPE_COLORS["preparer"]
_C_REV      = NOTE_TYPE_COLORS["reviewer"]
_C_DELIVERY = NOTE_TYPE_COLORS["delivery"]

# Which note types a role may CREATE
_CREATABLE: dict[str, list[str]] = {
    "preparer": ["preparer"],
    "reviewer": ["reviewer", "delivery"],
    "signer":   ["preparer", "reviewer", "delivery"],
}

# Labels for the type toggle buttons
_TYPE_LABELS: dict[str, str] = {
    "preparer": "Preparer",
    "reviewer": "Reviewer R",
    "delivery": "Delivery",
}


class NotesDock(QDockWidget):
    notes_changed = Signal()
    navigate_to   = Signal(str, str)

    def __init__(self, path: str | Path, job_id: str, performed_by: str,
                 role: str = "preparer", parent=None):
        super().__init__("Notes", parent)
        self._path         = Path(path)
        self._job_id       = job_id
        self._performed_by = performed_by
        self._role         = role
        self._filter       = "Open"

        self.setAllowedAreas(Qt.RightDockWidgetArea | Qt.LeftDockWidgetArea)
        self.setFeatures(
            QDockWidget.DockWidgetMovable |
            QDockWidget.DockWidgetFloatable |
            QDockWidget.DockWidgetClosable
        )
        self.setMinimumWidth(260)

        inner = QWidget()
        self._layout = QVBoxLayout(inner)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._build_header()
        self._build_list_area()
        self.setWidget(inner)
        self.reload()

    # ── Header ────────────────────────────────────────────────────────────

    def _build_header(self):
        hdr = QWidget()
        hdr.setStyleSheet(f"background: {_HEADER_BG};")
        hdr.setFixedHeight(36)
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(10, 0, 8, 0)
        hl.setSpacing(6)

        title = QLabel("Notes")
        title.setStyleSheet(
            "color: #FFFFFF; font-weight: bold; letter-spacing: 1px; font-size: 12px;"
        )
        hl.addWidget(title)
        hl.addStretch()

        self._btn_open = _filter_btn("Open", checked=True)
        self._btn_all  = _filter_btn("All",  checked=False)
        grp = QButtonGroup(self)
        grp.addButton(self._btn_open)
        grp.addButton(self._btn_all)
        grp.setExclusive(True)
        self._btn_open.clicked.connect(lambda: self._set_filter("Open"))
        self._btn_all.clicked.connect(lambda:  self._set_filter("All"))
        hl.addWidget(self._btn_open)
        hl.addWidget(self._btn_all)

        add_btn = QPushButton("+")
        add_btn.setFixedSize(22, 22)
        add_btn.setToolTip("Add note…")
        add_btn.setStyleSheet(
            "background: transparent; color: #FFFFFF; font-size: 15px; "
            "font-weight: bold; border: 1px solid #FFFFFF; border-radius: 11px; padding: 0;"
        )
        add_btn.clicked.connect(self._on_add_note)
        hl.addWidget(add_btn)
        self._layout.addWidget(hdr)

    # ── List area ─────────────────────────────────────────────────────────

    def _build_list_area(self):
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setFrameShape(QFrame.NoFrame)
        self._scroll_area.setStyleSheet("background: #F5F5F5;")

        self._cards_widget = QWidget()
        self._cards_widget.setStyleSheet("background: #F5F5F5;")
        self._cards_layout = QVBoxLayout(self._cards_widget)
        self._cards_layout.setContentsMargins(6, 6, 6, 6)
        self._cards_layout.setSpacing(6)
        self._cards_layout.addStretch()

        self._scroll_area.setWidget(self._cards_widget)
        self._layout.addWidget(self._scroll_area, 1)

        self._empty_lbl = QLabel("No open notes.")
        self._empty_lbl.setAlignment(Qt.AlignCenter)
        self._empty_lbl.setStyleSheet(
            "color: #888888; font-style: italic; padding: 20px;"
        )
        self._empty_lbl.setVisible(False)
        self._layout.addWidget(self._empty_lbl)

    # ── Public API ────────────────────────────────────────────────────────

    def reload(self):
        while self._cards_layout.count() > 1:
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        with db_connection(self._path) as conn:
            notes = get_notes(conn, self._job_id, self._filter)

        if not notes:
            self._empty_lbl.setText(
                "No open notes." if self._filter == "Open" else "No notes."
            )
            self._empty_lbl.setVisible(True)
            self._scroll_area.setVisible(False)
        else:
            self._empty_lbl.setVisible(False)
            self._scroll_area.setVisible(True)
            for note in notes:
                card = _NoteCard(note, self._performed_by, self._role)
                card.clear_requested.connect(self._on_clear)
                card.resolve_requested.connect(self._on_resolve)
                card.navigate_requested.connect(self.navigate_to)
                self._cards_layout.insertWidget(
                    self._cards_layout.count() - 1, card
                )

    def add_note(self, note_dict: dict):
        self.reload()
        self.notes_changed.emit()

    # ── Internal ──────────────────────────────────────────────────────────

    def _set_filter(self, f: str):
        self._filter = f
        self.reload()

    def _on_clear(self, note_id: str):
        with db_connection(self._path) as conn:
            clear_note(conn, note_id, self._performed_by)
        self.reload()
        self.notes_changed.emit()

    def _on_resolve(self, note_id: str):
        with db_connection(self._path) as conn:
            resolve_note(conn, note_id, self._performed_by)
        self.reload()
        self.notes_changed.emit()

    def _on_add_note(self):
        dlg = _PanelNoteDialog(self._path, self._job_id, self._performed_by,
                               role=self._role, parent=self)
        if dlg.exec() != _PanelNoteDialog.Accepted:
            return
        with db_connection(self._path) as conn:
            create_note(
                conn,
                job_id=self._job_id,
                body=dlg.note_text(),
                created_by=self._performed_by,
                linked_to_type=dlg.linked_to_type(),
                linked_to_id=dlg.linked_to_id(),
                note_type=dlg.note_type(),
            )
        self.reload()
        self.notes_changed.emit()


# ── Note card ─────────────────────────────────────────────────────────────────

class _NoteCard(QFrame):
    clear_requested   = Signal(str)
    resolve_requested = Signal(str)
    navigate_requested = Signal(str, str)

    def __init__(self, note: dict, performed_by: str, role: str = "preparer",
                 parent=None):
        super().__init__(parent)
        ntype    = note.get("note_type", "preparer")
        is_open  = note["status"] == "Open"
        is_closed = not is_open

        accent = NOTE_TYPE_COLORS.get(ntype, _C_PREP)
        bg     = "#F0F0F0" if is_closed else "#FFFFFF"

        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            f"QFrame {{ background: {bg}; border: 1px solid #D0D0D0; "
            f"border-radius: 4px; border-left: 3px solid {accent}; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # top row: badge + linked entity + date
        top_row = QHBoxLayout()

        if ntype in ("reviewer", "delivery"):
            badge_char = "R" if ntype == "reviewer" else "D"
            badge = QLabel(badge_char)
            badge.setFixedSize(18, 18)
            badge.setAlignment(Qt.AlignCenter)
            badge.setStyleSheet(
                f"background: {accent}; color: #FFFFFF; font-weight: bold; "
                "font-size: 10px; border-radius: 9px; border: none;"
            )
            top_row.addWidget(badge)

        linked = note.get("linked_display") or "—"
        entity_lbl = QLabel(linked)
        entity_lbl.setStyleSheet(
            f"font-weight: bold; font-size: 11px; color: {accent}; border: none;"
        )
        entity_lbl.setWordWrap(True)

        import datetime as _dt
        try:
            ts = _dt.datetime.fromisoformat(note["created_at"].replace("Z", "+00:00"))
            date_str = ts.strftime("%m/%d/%y")
        except Exception:
            date_str = ""
        date_lbl = QLabel(date_str)
        date_lbl.setStyleSheet("font-size: 10px; color: #888888; border: none;")
        date_lbl.setAlignment(Qt.AlignRight | Qt.AlignTop)

        top_row.addWidget(entity_lbl, 1)
        top_row.addWidget(date_lbl)
        layout.addLayout(top_row)

        # body
        body_lbl = QLabel(note["body"])
        body_lbl.setWordWrap(True)
        text_color = "#888888" if is_closed else "#000000"
        body_lbl.setStyleSheet(f"font-size: 12px; color: {text_color}; border: none;")
        if is_closed:
            f = body_lbl.font()
            f.setStrikeOut(True)
            body_lbl.setFont(f)
        layout.addWidget(body_lbl)

        if is_closed:
            who = note.get("resolved_by") or note.get("cleared_by") or ""
            action = "Resolved" if note["status"] == "Resolved" else "Cleared"
            if who:
                closed_lbl = QLabel(f"{action} by {who}")
                closed_lbl.setStyleSheet(
                    "font-size: 10px; color: #AAAAAA; font-style: italic; border: none;"
                )
                layout.addWidget(closed_lbl)

        # action row
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)

        if note.get("linked_to_type") and note.get("linked_to_id"):
            nav_btn = QPushButton("→ Go to")
            nav_btn.setStyleSheet(
                f"background: transparent; color: {accent}; font-size: 11px; "
                "font-weight: bold; border: none; padding: 0;"
            )
            nav_btn.setCursor(Qt.PointingHandCursor)
            nav_btn.clicked.connect(
                lambda: self.navigate_requested.emit(
                    note["linked_to_type"], note["linked_to_id"]
                )
            )
            btn_row.addWidget(nav_btn)

        btn_row.addStretch()

        if is_open:
            action_btn = _action_button_for(ntype, role)
            if action_btn is not None:
                sig = (self.resolve_requested if action_btn[1] == "resolve"
                       else self.clear_requested)
                btn = QPushButton(action_btn[0])
                btn.setStyleSheet(
                    f"background: {action_btn[2]}; color: #FFFFFF; font-size: 11px; "
                    "font-weight: bold; padding: 2px 8px; border-radius: 2px;"
                )
                btn.clicked.connect(lambda: sig.emit(note["note_id"]))
                btn_row.addWidget(btn)

        layout.addLayout(btn_row)


def _action_button_for(note_type: str, role: str) -> tuple[str, str, str] | None:
    """Return (label, signal_name, color) or None if this role has no action."""
    if note_type == "preparer":
        if role == "preparer":
            return ("Clear", "clear", "#888888")
        return None
    if note_type == "reviewer":
        if role == "reviewer":
            return ("Resolve", "resolve", _C_REV)
        if role == "preparer":
            return ("Clear", "clear", "#888888")
        return None
    if note_type == "delivery":
        if role == "reviewer":
            return ("Done", "resolve", _C_DELIVERY)
        return None
    return None


# ── Panel note dialog ─────────────────────────────────────────────────────────

class _PanelNoteDialog(QDialog):
    """Add a note from the Notes panel with optional account/JE link."""

    def __init__(self, path, job_id: str, performed_by: str,
                 role: str = "preparer", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Note")
        self.setMinimumWidth(420)

        creatable = _CREATABLE.get(role, ["preparer"])

        with db_connection(path) as conn:
            self._accounts = [dict(r) for r in conn.execute(
                "SELECT account_id, account_number, account_name FROM accounts "
                "WHERE job_id=? ORDER BY account_number, account_name", (job_id,)
            ).fetchall()]
            self._entries = [dict(r) for r in conn.execute(
                "SELECT aje_id, entry_number, description FROM journal_entries "
                "WHERE job_id=? ORDER BY entry_type, entry_number", (job_id,)
            ).fetchall()]

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Note type toggle
        type_row = QHBoxLayout()
        type_row.addWidget(QLabel("Type:"))
        grp = QButtonGroup(self)
        grp.setExclusive(True)
        self._type_btns: list[tuple[str, QPushButton]] = []
        for i, ntype in enumerate(creatable):
            label = _TYPE_LABELS[ntype]
            color = NOTE_TYPE_COLORS.get(ntype, "#444444")
            btn   = _type_pill(label, checked=(i == 0), color=color)
            grp.addButton(btn)
            type_row.addWidget(btn)
            self._type_btns.append((ntype, btn))
        type_row.addStretch()
        layout.addLayout(type_row)

        # Link to
        layout.addWidget(QLabel("Link to:"))
        link_row = QHBoxLayout()
        link_grp = QButtonGroup(self)
        link_grp.setExclusive(True)
        self._rb_none = _link_pill("None")
        self._rb_acct = _link_pill("Account")
        self._rb_je   = _link_pill("Journal Entry")
        self._rb_none.setChecked(True)
        for b in (self._rb_none, self._rb_acct, self._rb_je):
            link_grp.addButton(b)
            link_row.addWidget(b)
        link_row.addStretch()
        layout.addLayout(link_row)

        self._acct_combo = QComboBox()
        self._acct_combo.addItem("— select account —", None)
        for a in self._accounts:
            num = (a.get("account_number") or "").strip()
            name = a["account_name"].strip()
            self._acct_combo.addItem(f"{num}  {name}" if num else name, a["account_id"])
        self._acct_combo.setVisible(False)
        layout.addWidget(self._acct_combo)

        self._je_combo = QComboBox()
        self._je_combo.addItem("— select entry —", None)
        for e in self._entries:
            self._je_combo.addItem(
                f"{e['entry_number']}  {e['description']}", e["aje_id"]
            )
        self._je_combo.setVisible(False)
        layout.addWidget(self._je_combo)

        self._rb_none.toggled.connect(self._update_combos)
        self._rb_acct.toggled.connect(self._update_combos)
        self._rb_je.toggled.connect(self._update_combos)

        # ── Formatting toolbar ───────────────────────────────────────────
        fmt_bar = QHBoxLayout()
        fmt_bar.setSpacing(4)
        _BTN_FMT = (
            "QPushButton { font-weight: bold; font-size: 12px; padding: 2px 8px; "
            "border: 1px solid #BBBBBB; border-radius: 3px; background: #F5F5F5; min-width: 28px; } "
            "QPushButton:checked { background: #1A2B4C; color: #FFFFFF; border-color: #1A2B4C; } "
            "QPushButton:hover { background: #E0E8F8; }"
        )
        btn_bold = QPushButton("B")
        btn_bold.setStyleSheet(_BTN_FMT + "QPushButton { font-weight: bold; }")
        btn_bold.setCheckable(True)
        btn_bold.setToolTip("Bold (Ctrl+B)")
        btn_ital = QPushButton("I")
        btn_ital.setStyleSheet(_BTN_FMT + "QPushButton { font-style: italic; }")
        btn_ital.setCheckable(True)
        btn_ital.setToolTip("Italic (Ctrl+I)")
        btn_ul = QPushButton("U̲")
        btn_ul.setStyleSheet(_BTN_FMT)
        btn_ul.setCheckable(True)
        btn_ul.setToolTip("Underline (Ctrl+U)")
        for b in (btn_bold, btn_ital, btn_ul):
            b.setFixedWidth(34)
            fmt_bar.addWidget(b)
        fmt_bar.addStretch()
        layout.addLayout(fmt_bar)

        self._body = QTextEdit()
        self._body.setPlaceholderText("Enter note…")
        self._body.setMinimumHeight(90)
        layout.addWidget(self._body)

        # Wire formatting buttons to QTextEdit rich-text actions
        btn_bold.clicked.connect(lambda: self._body.setFontWeight(
            700 if btn_bold.isChecked() else 400))
        btn_ital.clicked.connect(lambda: self._body.setFontItalic(btn_ital.isChecked()))
        btn_ul.clicked.connect(lambda: self._body.setFontUnderline(btn_ul.isChecked()))
        # Keep button checked state in sync when cursor moves into already-formatted text
        self._body.currentCharFormatChanged.connect(lambda fmt: (
            btn_bold.setChecked(fmt.fontWeight() >= 700),
            btn_ital.setChecked(fmt.fontItalic()),
            btn_ul.setChecked(fmt.fontUnderline()),
        ))

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

    def _update_combos(self):
        self._acct_combo.setVisible(self._rb_acct.isChecked())
        self._je_combo.setVisible(self._rb_je.isChecked())

    def note_text(self) -> str:
        # Return HTML if the user applied formatting, otherwise plain text
        plain = self._body.toPlainText().strip()
        html  = self._body.toHtml()
        # Only use HTML if it actually has formatting beyond the default wrapper
        if any(tag in html for tag in ("<b>", "<i>", "<u>", "font-weight:600", "font-weight:700")):
            return html
        return plain

    def note_type(self) -> str:
        for ntype, btn in self._type_btns:
            if btn.isChecked():
                return ntype
        return self._type_btns[0][0] if self._type_btns else "preparer"

    def linked_to_type(self) -> str | None:
        if self._rb_acct.isChecked():
            return "account"
        if self._rb_je.isChecked():
            return "journal_entry"
        return None

    def linked_to_id(self) -> str | None:
        if self._rb_acct.isChecked():
            return self._acct_combo.currentData()
        if self._rb_je.isChecked():
            return self._je_combo.currentData()
        return None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _type_pill(label: str, checked: bool, color: str) -> QPushButton:
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
            background: {color}; color: #FFFFFF; font-weight: bold;
            border-color: {color};
        }}
    """)
    return btn


def _link_pill(label: str) -> QPushButton:
    """Navy-background, white-text toggle button used for the 'Link to' selector."""
    btn = QPushButton(label)
    btn.setCheckable(True)
    btn.setFixedHeight(24)
    btn.setStyleSheet("""
        QPushButton {
            background: #1A2B4C; color: #FFFFFF;
            font-size: 11px; font-weight: bold; border: 1px solid #1A2B4C;
            border-radius: 3px; padding: 0 12px;
        }
        QPushButton:hover { background: #2A3B6C; }
        QPushButton:checked {
            background: #4A7A4A; border-color: #3A6A3A;
        }
    """)
    return btn


def _filter_btn(label: str, checked: bool) -> QPushButton:
    btn = QPushButton(label)
    btn.setCheckable(True)
    btn.setChecked(checked)
    btn.setFixedHeight(22)
    btn.setStyleSheet("""
        QPushButton {
            background: transparent; color: #FFFFFF;
            font-size: 11px; border: 1px solid #FFFFFF;
            border-radius: 2px; padding: 0 8px;
        }
        QPushButton:checked {
            background: #FFFFFF; color: #1A2B4C; font-weight: bold;
        }
    """)
    return btn
