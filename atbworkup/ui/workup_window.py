from __future__ import annotations

import json
import socket
import time
import uuid
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QFormLayout, QLabel, QStatusBar, QPushButton, QMessageBox,
    QTabWidget, QSplitter, QToolBar, QFileDialog, QDialog,
    QDialogButtonBox, QLineEdit, QComboBox,
)
from PySide6.QtCore import Qt, Signal

from atbworkup.constants import ENTITY_TYPES, WORKPAPER_ENTITY_TYPES
from atbworkup.utils.naming import STATUS_COLORS

_NAVY = "#1A2B4C"


class _FloatWindow(QMainWindow):
    """Minimal floating window that hosts a single widget pop-out."""

    def __init__(self, title: str, widget: QWidget, on_return, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self._widget    = widget
        self._on_return = on_return

        tb = QToolBar()
        tb.setMovable(False)
        tb.setStyleSheet(
            f"QToolBar {{ background: {_NAVY}; border: none; padding: 2px 6px; spacing: 4px; }}"
        )
        self.addToolBar(tb)

        btn = QPushButton("↩  Return to Main Window")
        btn.setStyleSheet(
            "background: #FFFFFF; color: #1A2B4C; font-weight: bold; "
            "padding: 4px 14px; border-radius: 3px; border: none;"
        )
        btn.clicked.connect(self._do_return)
        tb.addWidget(btn)

        self.setCentralWidget(widget)

    def closeEvent(self, event):
        # Clicking the OS close button on a pop-out should fold it back into
        # the main window rather than destroying it. But when the main
        # window is itself closing, it nulls _on_return first and calls
        # close() on every pop-out expecting them to actually go away — if
        # we always ignore() here, that never happens and pop-outs survive
        # the main window closing.
        if self._on_return is not None:
            self._do_return()
            event.ignore()
        else:
            event.accept()

    def _do_return(self):
        fn = self._on_return
        if fn:
            self._on_return = None
            fn()

_ENTITY_LABELS = {code: label for code, label in ENTITY_TYPES}

# ── Workflow transitions ───────────────────────────────────────────────────────
# Each entry: (button_label, new_status, style_key)
# Shown regardless of role — users know their own role.
_TRANSITIONS: dict[str, list[tuple[str, str, str]]] = {
    "Preparation in Progress": [
        ("Submit for Review",    "Ready for Review",   "navy"),
    ],
    "Ready for Review": [
        ("Return — Clear Notes", "Clear Notes",        "amber"),
        ("Approve for Delivery", "Ready for Delivery", "green"),
    ],
    "Clear Notes": [
        ("Mark Notes Cleared",   "Notes Cleared",      "navy"),
    ],
    "Notes Cleared": [
        ("Resubmit for Review",  "Ready for Review",   "navy"),
        ("Approve for Delivery", "Ready for Delivery", "green"),
    ],
    "Ready for Delivery": [
        ("Finalize & Lock",      "Finalized",          "red"),
    ],
    "Finalized": [],
}

_BTN_STYLES: dict[str, str] = {
    "navy":  "background:#1A2B4C;color:#FFF;font-weight:bold;padding:5px 14px;border-radius:3px;",
    "green": "background:#2A6A4A;color:#FFF;font-weight:bold;padding:5px 14px;border-radius:3px;",
    "amber": "background:#B85C00;color:#FFF;font-weight:bold;padding:5px 14px;border-radius:3px;",
    "red":   "background:#7B1A1A;color:#FFF;font-weight:bold;padding:5px 14px;border-radius:3px;",
}


class WorkupWindow(QMainWindow):
    """Main window for an open workup file."""

    def __init__(self, path: str | Path, job: dict,
                 source_xlsx: str | Path | None = None,
                 role: str = "preparer",
                 performed_by: str | None = None,
                 parent=None):
        super().__init__(parent)
        self._path         = Path(path)
        self._source_xlsx  = Path(source_xlsx) if source_xlsx else None
        self._job          = job
        self._role         = role
        self._performed_by = performed_by or job.get("prepared_by", "")
        self._grid              = None
        self._je_panel          = None
        self._notes_dock        = None
        self._report_tab        = None
        self._workpapers_tab    = None
        self._transition_btns: list[QPushButton] = []
        # pop-out float windows
        self._report_float: _FloatWindow | None = None
        self._je_float:     _FloatWindow | None = None
        self._notes_float:  _FloatWindow | None = None
        # Pacing telemetry: a per-window session so grading can see how long
        # work on this file actually took, and from what machine, rather than
        # just "some activity happened at some point."
        self._session_id    = uuid.uuid4().hex
        self._session_start = time.monotonic()
        self._log_session_event("session_started")
        self._build_ui()

    def _log_session_event(self, event_type: str, **extra):
        from atbworkup.db.connection import db_connection
        from atbworkup.models.activity import log_activity
        hostname = socket.gethostname()
        metadata = {"session_id": self._session_id, "hostname": hostname, **extra}
        with db_connection(self._path) as conn:
            log_activity(
                conn,
                job_id=self._job["job_id"],
                event_type=event_type,
                description=f"{event_type.replace('_', ' ').title()} on {hostname}",
                performed_by=self._performed_by,
                metadata_json=json.dumps(metadata),
            )

    def closeEvent(self, event):
        duration = round(time.monotonic() - self._session_start, 1)
        self._log_session_event("session_ended", duration_seconds=duration)
        super().closeEvent(event)

    def _build_ui(self):
        self._update_title()
        self.setMinimumSize(1100, 640)

        self._main_splitter = QSplitter(Qt.Vertical)
        self._main_splitter.setChildrenCollapsible(False)
        self._main_splitter.setHandleWidth(4)

        self._tabs = QTabWidget()
        self._main_splitter.addWidget(self._tabs)
        self.setCentralWidget(self._main_splitter)

        # ── Tab 0: Job Info ──────────────────────────────────────────────
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setAlignment(Qt.AlignTop)

        group = QGroupBox("Job Information")
        form = QFormLayout(group)
        form.setLabelAlignment(Qt.AlignRight)

        def field(value):
            lbl = QLabel(str(value) if value else "—")
            lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            return lbl

        form.addRow("Client Name:",       field(self._job["client_name"]))
        form.addRow("Entity Name:",       field(self._job["entity_name"]))
        form.addRow("Tax Year:",          field(self._job["tax_year"]))
        form.addRow("Entity Type:",       field(_ENTITY_LABELS.get(
                                              self._job["entity_type"],
                                              self._job["entity_type"])))
        form.addRow("Prepared By:",       field(self._job["prepared_by"]))
        form.addRow("Reviewer:",          field(self._job["reviewer"]))
        form.addRow("Accounting System:", field(self._job["accounting_system"]))
        self._status_field = field(self._job["status"])
        form.addRow("Status:",            self._status_field)
        form.addRow("Version:",           field(f"V{self._job.get('workflow_version', 1):02d}"))
        form.addRow("Created:",           field(self._job["created_at"]))

        btn_row = QHBoxLayout()
        self._btn_import_tb = QPushButton("Import Trial Balance…")
        self._btn_import_tb.clicked.connect(self._on_import_tb)
        btn_row.addWidget(self._btn_import_tb)

        self._btn_edit_account = QPushButton("Edit Account…")
        self._btn_edit_account.clicked.connect(self._on_edit_account)
        self._btn_edit_account.setEnabled(False)
        btn_row.addWidget(self._btn_edit_account)
        btn_row.addStretch()

        info_layout.addWidget(group)
        info_layout.addLayout(btn_row)
        info_layout.addStretch()

        self._tabs.addTab(info_widget, "Job Info")

        # ── Tab 1: Trial Balance ─────────────────────────────────────────
        self._fs_tab_index          = 1
        self._report_tab_index      = 2
        self._audit_tab_index       = 3
        self._workpapers_tab_index  = 4
        self._audit_tab             = None
        self._rebuild_fs_tab()

        # ── Tab 2: Reports ───────────────────────────────────────────────
        self._rebuild_report_tab()

        # ── Tab 3: Audit Log ─────────────────────────────────────────────
        self._rebuild_audit_tab()

        # ── Tab 4: Workpapers (1065 / 1120S / 1120 only) ─────────────────
        self._rebuild_workpapers_tab()

        # ── Pop-out corner button for tab widget ────────────────────────
        self._popout_corner_btn = QPushButton("⬜  Pop Out")
        self._popout_corner_btn.setToolTip("Open this panel in a separate window")
        self._popout_corner_btn.setStyleSheet(
            f"background: {_NAVY}; color: #FFFFFF; font-weight: bold; "
            "font-size: 11px; padding: 2px 10px; border-radius: 3px; border: none; margin: 2px;"
        )
        self._popout_corner_btn.setVisible(False)
        self._popout_corner_btn.clicked.connect(self._on_popout_current_tab)
        self._tabs.setCornerWidget(self._popout_corner_btn)
        self._tabs.currentChanged.connect(self._on_tab_changed_popout)

        # ── JE panel ────────────────────────────────────────────────────
        self._rebuild_je_panel()

        # ── Notes dock ──────────────────────────────────────────────────
        self._rebuild_notes_dock()

        # ── Toolbar ─────────────────────────────────────────────────────
        self._build_toolbar()

        # status bar
        sb = QStatusBar()
        from atbworkup.constants import ROLE_COLORS
        role_color = ROLE_COLORS.get(self._role, "#444444")
        role_label = QLabel(f"  {self._role.capitalize()}  ")
        role_label.setStyleSheet(
            f"color: #FFFFFF; background: {role_color}; font-weight: bold; "
            "padding: 2px 6px; border-radius: 3px; font-size: 11px;"
        )
        sb.addPermanentWidget(role_label)
        user_label = QLabel(f"  {self._performed_by}  ")
        user_label.setStyleSheet("color: #FFFFFF; font-size: 11px;")
        sb.addPermanentWidget(user_label)
        sb.showMessage(str(self._source_xlsx or self._path))
        self.setStatusBar(sb)

    # ── Title / status display ────────────────────────────────────────────

    def _update_title(self):
        status   = self._job.get("status", "Preparation in Progress")
        version  = self._job.get("workflow_version", 1)
        self._base_title = (
            f"{self._job['tax_year']} {self._job['client_name']} "
            f"— {status}  V{version:02d}"
        )
        self.setWindowTitle(self._base_title)

    def _refresh_status_display(self):
        status  = self._job.get("status", "Preparation in Progress")
        version = self._job.get("workflow_version", 1)
        self._status_field.setText(status)
        self._update_title()
        # Update status pill in toolbar
        color = STATUS_COLORS.get(status, "#5A6A8A")
        self._status_pill.setText(f"  {status}  V{version:02d}  ")
        self._status_pill.setStyleSheet(
            f"color:#FFFFFF; background:{color}; font-weight:bold; "
            "padding:2px 8px; border-radius:3px; font-size:11px;"
        )
        # Rebuild transition buttons
        for btn in self._transition_btns:
            btn.setParent(None)
        self._transition_btns.clear()
        transitions = _TRANSITIONS.get(status, [])
        locked = (status == "Finalized")
        self._save_btn.setEnabled(not locked and self._source_xlsx is not None)
        for label, new_status, style in transitions:
            btn = QPushButton(label)
            btn.setStyleSheet(_BTN_STYLES[style])
            btn.clicked.connect(
                lambda _checked=False, ns=new_status, lb=label: self._on_transition(ns, lb)
            )
            self._toolbar_ref.addWidget(btn)
            self._transition_btns.append(btn)

    # ── Toolbar ───────────────────────────────────────────────────────────

    def _build_toolbar(self):
        tb = QToolBar("Main")
        tb.setMovable(False)
        tb.setStyleSheet(
            "QToolBar { background: #E5E5E5; border-bottom: 1px solid #cccccc; "
            "padding: 2px 6px; spacing: 6px; }"
        )
        self.addToolBar(tb)
        self._toolbar_ref = tb

        self._save_btn = QPushButton("Save")
        self._save_btn.setStyleSheet(
            "background:#4A7A4A;color:#FFFFFF;font-weight:bold;"
            "padding:5px 14px;border-radius:3px;"
        )
        self._save_btn.setEnabled(self._source_xlsx is not None)
        self._save_btn.clicked.connect(self._on_save)
        tb.addWidget(self._save_btn)

        # Spacer
        spacer = QWidget()
        spacer.setFixedWidth(12)
        tb.addWidget(spacer)

        # Status pill
        self._status_pill = QLabel()
        tb.addWidget(self._status_pill)

        spacer2 = QWidget()
        spacer2.setFixedWidth(12)
        tb.addWidget(spacer2)

        # Initial transition buttons painted here
        self._refresh_status_display()

    # ── Trial Balance tab ─────────────────────────────────────────────────

    def _rebuild_fs_tab(self):
        if self._tabs.count() > self._fs_tab_index:
            self._tabs.removeTab(self._fs_tab_index)

        from atbworkup.db.connection import db_connection
        with db_connection(self._path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM accounts WHERE job_id = ?",
                (self._job["job_id"],),
            ).fetchone()[0]

        if count == 0:
            placeholder = QLabel(
                "No trial balance imported yet.\n"
                "Use 'Import Trial Balance…' on the Job Info tab."
            )
            placeholder.setAlignment(Qt.AlignCenter)
            self._tabs.insertTab(self._fs_tab_index, placeholder, "Trial Balance")
        else:
            from atbworkup.ui.financial_grid import FinancialGrid
            self._grid = FinancialGrid(
                self._path, self._job["job_id"],
                self._job["entity_type"], self._job["prepared_by"],
            )
            self._grid.je_requested.connect(self._on_je_requested)
            self._grid.note_requested.connect(self._on_note_requested)
            self._grid.account_created.connect(self._on_account_created)
            self._tabs.insertTab(self._fs_tab_index, self._grid, "Trial Balance")
            self._refresh_reviewer_grid_flags()
            # Wire double-click for inline account editing
            try:
                self._grid.account_edit_requested.connect(self._on_edit_account_by_id)
            except AttributeError:
                pass  # older grid version without the signal

    # ── Reports tab ───────────────────────────────────────────────────────

    def _rebuild_report_tab(self):
        from atbworkup.db.connection import db_connection
        with db_connection(self._path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM accounts WHERE job_id = ?",
                (self._job["job_id"],),
            ).fetchone()[0]

        if self._tabs.count() > self._report_tab_index:
            self._tabs.removeTab(self._report_tab_index)
        self._report_tab = None

        if count == 0:
            return

        from atbworkup.ui.report_tab import ReportTab
        self._report_tab = ReportTab(self._path, self._job["job_id"], parent=self)
        self._report_tab.note_requested.connect(self._on_note_requested)
        self._report_tab.je_requested.connect(self._on_report_je_requested)
        self._tabs.insertTab(self._report_tab_index, self._report_tab, "Reports")

    def _reprint_report(self):
        if self._report_tab is not None:
            self._report_tab.reprint()

    def _on_report_je_requested(self, account_id: str, account_name: str):
        self._on_je_requested(account_id, "AJE")

    # ── Audit Log tab ─────────────────────────────────────────────────────

    def _rebuild_audit_tab(self):
        if self._tabs.count() > self._audit_tab_index:
            self._tabs.removeTab(self._audit_tab_index)
        self._audit_tab = None

        from atbworkup.ui.audit_log_tab import AuditLogTab
        self._audit_tab = AuditLogTab(self._path, self._job["job_id"], parent=self)
        self._tabs.insertTab(self._audit_tab_index, self._audit_tab, "Audit Log")
        self._tabs.currentChanged.connect(self._on_tab_changed)

    def _rebuild_workpapers_tab(self):
        # Remove if present
        for i in range(self._tabs.count()):
            if self._tabs.tabText(i) == "Workpapers":
                self._tabs.removeTab(i)
                break
        self._workpapers_tab = None

        entity_type = self._job.get("entity_type", "")
        if entity_type not in WORKPAPER_ENTITY_TYPES:
            return

        from atbworkup.db.connection import db_connection
        with db_connection(self._path) as conn:
            has_accounts = conn.execute(
                "SELECT COUNT(*) FROM accounts WHERE job_id = ?",
                (self._job["job_id"],),
            ).fetchone()[0] > 0

        if not has_accounts:
            return

        from atbworkup.ui.workpapers_tab import WorkpapersTab
        self._workpapers_tab = WorkpapersTab(
            self._path, self._job["job_id"], entity_type, parent=self
        )
        self._tabs.addTab(self._workpapers_tab, "Workpapers")

    def _on_tab_changed(self, index: int):
        if index == self._audit_tab_index and self._audit_tab is not None:
            self._audit_tab.refresh()
        wp_idx = next(
            (i for i in range(self._tabs.count()) if self._tabs.tabText(i) == "Workpapers"),
            -1,
        )
        if index == wp_idx and self._workpapers_tab is not None:
            self._workpapers_tab.refresh()

    def _refresh_audit_log(self):
        if self._audit_tab is not None:
            self._audit_tab.refresh()

    # ── JE panel ──────────────────────────────────────────────────────────

    def _rebuild_je_panel(self):
        from atbworkup.db.connection import db_connection
        with db_connection(self._path) as conn:
            has_accounts = conn.execute(
                "SELECT COUNT(*) FROM accounts WHERE job_id = ?",
                (self._job["job_id"],),
            ).fetchone()[0] > 0

        if not has_accounts or self._je_panel is not None:
            return

        from atbworkup.ui.je_panel import JEPanel
        self._je_panel = JEPanel(
            self._path, self._job["job_id"], self._job["prepared_by"],
        )
        self._je_panel.setMinimumHeight(32)
        self._je_panel.entries_changed.connect(self._on_entries_changed)
        self._je_panel.note_requested.connect(self._on_note_requested_je)

        # Wrap in container with pop-out button in header
        self._je_container = QWidget()
        cl = QVBoxLayout(self._je_container)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)

        je_hdr = QWidget()
        je_hdr.setFixedHeight(28)
        je_hdr.setStyleSheet(f"background: {_NAVY};")
        je_hl = QHBoxLayout(je_hdr)
        je_hl.setContentsMargins(10, 0, 6, 0)
        je_title = QLabel("Journal Entries")
        je_title.setStyleSheet("color: #FFFFFF; font-weight: bold; font-size: 11px; letter-spacing: 1px;")
        je_hl.addWidget(je_title)
        je_hl.addStretch()
        _hdr_btn_style = (
            "background: rgba(255,255,255,0.15); color: #FFFFFF; font-size: 10px; "
            "font-weight: bold; padding: 0 8px; border-radius: 3px; border: none;"
        )
        self._je_popout_btn = QPushButton("⬜  Pop Out")
        self._je_popout_btn.setToolTip("Open Journal Entries in a separate window")
        self._je_popout_btn.setFixedHeight(20)
        self._je_popout_btn.setStyleSheet(_hdr_btn_style)
        self._je_popout_btn.clicked.connect(self._on_popout_je)
        je_hl.addWidget(self._je_popout_btn)

        self._je_hide_btn = QPushButton("▼  Hide")
        self._je_hide_btn.setToolTip("Collapse / show the Journal Entries panel")
        self._je_hide_btn.setFixedHeight(20)
        self._je_hide_btn.setStyleSheet(_hdr_btn_style)
        self._je_hide_btn.clicked.connect(self._on_toggle_je_panel)
        je_hl.addWidget(self._je_hide_btn)

        cl.addWidget(je_hdr)
        cl.addWidget(self._je_panel, 1)

        self._je_container.setMinimumHeight(32)
        self._main_splitter.setChildrenCollapsible(True)
        self._main_splitter.addWidget(self._je_container)
        self._main_splitter.setSizes([440, 260])

    def _on_entries_changed(self):
        if self._grid:
            self._grid.refresh()
        self._reprint_report()
        self._refresh_audit_log()

    def _on_je_requested(self, account_id: str, entry_type: str):
        if self._je_panel:
            self._je_panel.open_for_account(account_id, entry_type)
            if self._je_float:
                self._je_float.show()
                self._je_float.raise_()
            else:
                sizes = self._main_splitter.sizes()
                if sizes[-1] < 50:
                    self._je_panel.set_body_visible(True)
                    total = sum(sizes)
                    self._main_splitter.setSizes([total - 260, 260])
                    if hasattr(self, "_je_hide_btn"):
                        self._je_hide_btn.setText("▼  Hide")

    def _on_account_created(self):
        """Reload JE panel account list so newly created accounts are immediately selectable."""
        if self._je_panel:
            self._je_panel.reload_accounts()

    def _on_toggle_je_panel(self):
        """Collapse or restore the JE panel within the splitter."""
        sizes = self._main_splitter.sizes()
        if not sizes:
            return
        _WRAPPER_HDR_H = 28
        if sizes[-1] > _WRAPPER_HDR_H + 4:
            # Collapse: remember height, hide the panel's own body, shrink to wrapper header only
            self._je_last_height = sizes[-1]
            total = sum(sizes)
            if self._je_panel:
                self._je_panel.set_body_visible(False)
            self._main_splitter.setSizes([total - _WRAPPER_HDR_H, _WRAPPER_HDR_H])
            self._je_hide_btn.setText("▲  Show")
        else:
            restored = getattr(self, "_je_last_height", 260)
            total = sum(sizes)
            if self._je_panel:
                self._je_panel.set_body_visible(True)
            self._main_splitter.setSizes([total - restored, restored])
            self._je_hide_btn.setText("▼  Hide")

    # ── Notes dock ────────────────────────────────────────────────────────

    def _rebuild_notes_dock(self):
        from atbworkup.db.connection import db_connection
        with db_connection(self._path) as conn:
            has_accounts = conn.execute(
                "SELECT COUNT(*) FROM accounts WHERE job_id = ?",
                (self._job["job_id"],),
            ).fetchone()[0] > 0

        if not has_accounts or self._notes_dock is not None:
            return

        from atbworkup.ui.notes_panel import NotesDock
        self._notes_dock = NotesDock(
            self._path, self._job["job_id"], self._performed_by,
            role=self._role,
            parent=self,
        )
        self._notes_dock.notes_changed.connect(self._refresh_notes_badge)
        self._notes_dock.notes_changed.connect(self._refresh_reviewer_grid_flags)
        self._notes_dock.notes_changed.connect(self._reprint_report)
        self._notes_dock.navigate_to.connect(self._on_notes_navigate)

        # Custom title bar with pop-out button
        notes_tb = QWidget()
        notes_tb.setFixedHeight(28)
        notes_tb.setStyleSheet(f"background: {_NAVY};")
        notes_tbl = QHBoxLayout(notes_tb)
        notes_tbl.setContentsMargins(10, 0, 6, 0)
        notes_lbl = QLabel("Notes")
        notes_lbl.setStyleSheet("color: #FFFFFF; font-weight: bold; font-size: 11px; letter-spacing: 1px;")
        notes_tbl.addWidget(notes_lbl)
        notes_tbl.addStretch()
        self._notes_popout_btn = QPushButton("⬜  Pop Out")
        self._notes_popout_btn.setToolTip("Open Notes in a separate window")
        self._notes_popout_btn.setFixedHeight(20)
        self._notes_popout_btn.setStyleSheet(
            "background: rgba(255,255,255,0.15); color: #FFFFFF; font-size: 10px; "
            "font-weight: bold; padding: 0 8px; border-radius: 3px; border: none;"
        )
        self._notes_popout_btn.clicked.connect(self._on_popout_notes)
        notes_tbl.addWidget(self._notes_popout_btn)
        self._notes_dock.setTitleBarWidget(notes_tb)

        self.addDockWidget(Qt.RightDockWidgetArea, self._notes_dock)
        self._refresh_notes_badge()

    def _refresh_notes_badge(self):
        from atbworkup.db.connection import db_connection
        from atbworkup.models.notes import open_note_count
        with db_connection(self._path) as conn:
            n = open_note_count(conn, self._job["job_id"])
        if n:
            self.setWindowTitle(f"{self._base_title}  ({n} open note{'s' if n != 1 else ''})")
        else:
            self.setWindowTitle(self._base_title)

    def _refresh_reviewer_grid_flags(self):
        if not self._grid:
            return
        from atbworkup.db.connection import db_connection
        from atbworkup.models.notes import reviewer_note_account_ids
        with db_connection(self._path) as conn:
            ids = reviewer_note_account_ids(conn, self._job["job_id"])
        self._grid.set_reviewer_note_ids(ids)

    def _on_notes_navigate(self, linked_type: str, linked_id: str):
        if linked_type == "account" and self._grid:
            self._tabs.setCurrentIndex(self._fs_tab_index)
            self._grid.navigate_to_account(linked_id)

    # ── Pop-out panel handlers ───────────────────────────────────────────

    def _on_tab_changed_popout(self, index: int):
        """Show/hide the corner pop-out button based on whether Reports tab is active."""
        is_reports = (
            self._report_tab is not None
            and self._tabs.widget(index) is self._report_tab
        )
        is_floating = self._report_float is not None
        self._popout_corner_btn.setVisible(is_reports or is_floating)
        if is_floating:
            self._popout_corner_btn.setText("↩  Return to Main")
        else:
            self._popout_corner_btn.setText("⬜  Pop Out")

    def _on_popout_current_tab(self):
        if self._report_float:
            self._pop_in_report()
        else:
            self._pop_out_report()

    def _pop_out_report(self):
        if self._report_tab is None or self._report_float:
            return
        idx = self._tabs.indexOf(self._report_tab)
        if idx < 0:
            return

        # Replace with placeholder
        ph = QLabel(
            "Reports panel is open in a separate window.\n\n"
            "Click  ↩ Return to Main  in the floating window to bring it back.\n"
            "Or use the  ↩ Return to Main  button above."
        )
        ph.setAlignment(Qt.AlignCenter)
        ph.setStyleSheet("color: #888; font-size: 13px;")
        self._tabs.insertTab(idx, ph, "Reports  ↗")
        self._tabs.removeTab(idx + 1)
        self._tabs.setCurrentIndex(idx)

        self._report_float = _FloatWindow(
            f"Reports — {self._job['client_name']} {self._job['tax_year']}",
            self._report_tab,
            self._pop_in_report,
            parent=None,
        )
        self._report_float.resize(1000, 720)
        self._report_float.show()
        self._popout_corner_btn.setText("↩  Return to Main")

    def _pop_in_report(self):
        if self._report_float is None or self._report_tab is None:
            return
        # Find placeholder tab
        ph_idx = next(
            (i for i in range(self._tabs.count()) if "↗" in self._tabs.tabText(i)),
            self._report_tab_index,
        )
        self._tabs.insertTab(ph_idx, self._report_tab, "Reports")
        self._tabs.removeTab(ph_idx + 1)
        self._tabs.setCurrentIndex(ph_idx)
        self._report_float.centralWidget()  # avoid double-free
        self._report_float._on_return = None
        self._report_float.hide()
        self._report_float.deleteLater()
        self._report_float = None
        self._popout_corner_btn.setText("⬜  Pop Out")

    def _on_popout_je(self):
        if self._je_float:
            self._pop_in_je()
        else:
            self._pop_out_je()

    def _pop_out_je(self):
        if self._je_panel is None or self._je_float:
            return
        # Remove je_panel from container so it can be reparented
        self._je_container.layout().removeWidget(self._je_panel)
        # Collapse the container in the splitter
        sizes = self._main_splitter.sizes()
        self._je_container.hide()

        self._je_float = _FloatWindow(
            f"Journal Entries — {self._job['client_name']} {self._job['tax_year']}",
            self._je_panel,
            self._pop_in_je,
            parent=None,
        )
        self._je_float.resize(900, 500)
        self._je_float.show()
        self._je_popout_btn.setText("↩  Return")

    def _pop_in_je(self):
        if self._je_float is None or self._je_panel is None:
            return
        # Re-add je_panel to container
        self._je_container.layout().addWidget(self._je_panel, 1)
        self._je_container.show()
        sizes = self._main_splitter.sizes()
        if sum(sizes) > 0 and sizes[-1] < 50:
            total = sum(sizes)
            self._main_splitter.setSizes([total - 260, 260])
        self._je_float._on_return = None
        self._je_float.hide()
        self._je_float.deleteLater()
        self._je_float = None
        self._je_popout_btn.setText("⬜  Pop Out")

    def _on_popout_notes(self):
        if self._notes_float:
            self._pop_in_notes()
        else:
            self._pop_out_notes()

    def _pop_out_notes(self):
        if self._notes_dock is None or self._notes_float:
            return
        # Get the inner content widget from the dock
        inner = self._notes_dock.widget()
        if inner is None:
            return
        self._notes_dock.hide()

        self._notes_float = _FloatWindow(
            f"Notes — {self._job['client_name']} {self._job['tax_year']}",
            inner,
            self._pop_in_notes,
            parent=None,
        )
        self._notes_float.resize(420, 650)
        self._notes_float.show()
        self._notes_popout_btn.setText("↩  Return")

    def _pop_in_notes(self):
        if self._notes_float is None or self._notes_dock is None:
            return
        inner = self._notes_float.centralWidget()
        if inner is not None:
            self._notes_dock.setWidget(inner)
        self._notes_dock.show()
        self._notes_float._on_return = None
        self._notes_float.hide()
        self._notes_float.deleteLater()
        self._notes_float = None
        self._notes_popout_btn.setText("⬜  Pop Out")

    # ── Add Note handlers ────────────────────────────────────────────────

    def _on_note_requested(self, account_id: str, account_name: str):
        self._add_note(
            context_label=account_name,
            linked_to_type="account",
            linked_to_id=account_id,
        )

    def _on_note_requested_je(self, aje_id: str, label: str):
        self._add_note(
            context_label=label,
            linked_to_type="journal_entry",
            linked_to_id=aje_id,
        )

    def _add_note(self, *, context_label: str, linked_to_type: str, linked_to_id: str):
        from atbworkup.ui.add_note_dialog import AddNoteDialog
        from atbworkup.db.connection import db_connection
        from atbworkup.models.notes import create_note
        from atbworkup.models.activity import log_activity

        dlg = AddNoteDialog(context_label, role=self._role, parent=self)
        if dlg.exec() != AddNoteDialog.Accepted:
            return

        note_type = dlg.note_type()
        with db_connection(self._path) as conn:
            note = create_note(
                conn,
                job_id=self._job["job_id"],
                body=dlg.note_text(),
                created_by=self._performed_by,
                linked_to_type=linked_to_type,
                linked_to_id=linked_to_id,
                note_type=note_type,
            )
            log_activity(
                conn,
                job_id=self._job["job_id"],
                event_type=f"added_{note_type}_note",
                description=f"Added {note_type} note on {linked_to_type}: {context_label}",
                performed_by=self._performed_by,
            )

        if self._notes_dock:
            self._notes_dock.add_note(note)
            self._notes_dock.show()
            self._notes_dock.raise_()
        self._refresh_notes_badge()
        self._refresh_reviewer_grid_flags()

    # ── Save ──────────────────────────────────────────────────────────────

    def _on_save(self):
        if not self._source_xlsx:
            return
        if getattr(self, "_saving", False):
            return   # a save is already in flight — a second one could
                      # interleave its write with the first and corrupt both
        self._saving = True
        self._save_btn.setEnabled(False)
        from atbworkup.db.connection import db_connection
        from atbworkup.exporter.review_package import save_workup
        try:
            with db_connection(self._path) as conn:
                save_workup(
                    conn,
                    job=self._job,
                    output_path=self._source_xlsx,
                    performed_by=self._performed_by,
                )
            # Confirm the file we just wrote is actually openable before
            # declaring success — catches a corrupted save immediately
            # instead of the next time someone opens it.
            import zipfile
            with zipfile.ZipFile(self._source_xlsx) as z:
                bad_entry = z.testzip()
            if bad_entry is not None:
                raise RuntimeError(
                    f"the saved file failed its own integrity check (bad entry: {bad_entry})"
                )
            self.statusBar().showMessage(f"Saved — {self._source_xlsx}")
        except Exception as exc:
            QMessageBox.critical(self, "Save Error", f"Failed to save:\n{exc}")
        finally:
            self._saving = False
            self._refresh_status_display()

    def closeEvent(self, event):
        # Close any pop-out panels too — nulling _on_return first means
        # _FloatWindow.closeEvent() accepts the close instead of treating it
        # as a "return to main" click.
        for fw in (self._report_float, self._je_float, self._notes_float):
            if fw:
                fw._on_return = None
                fw.close()
                fw.deleteLater()
        if self._source_xlsx and self._job.get("status") != "Finalized":
            try:
                self._on_save()
            except Exception:
                pass
        if self._path and self._path.exists():
            try:
                self._path.unlink()
            except Exception:
                pass
        event.accept()

    # ── Workflow transitions ───────────────────────────────────────────────

    def _on_transition(self, new_status: str, label: str):
        if new_status == "Finalized":
            self._on_finalize()
            return

        reply = QMessageBox.question(
            self, "Confirm Status Change",
            f'Change status to "{new_status}"?\n\n'
            "The file will be saved with a new version number.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self._execute_transition(new_status)

    def _on_finalize(self):
        """Stern finalize/lock confirmation."""
        import datetime
        dlg = _FinalizeConfirmDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        self._execute_transition("Finalized", lock=True)

    def _execute_transition(self, new_status: str, lock: bool = False):
        from atbworkup.db.connection import db_connection
        from atbworkup.exporter.review_package import transition_workup_status
        from atbworkup.models.job import get_job

        if not self._source_xlsx:
            QMessageBox.warning(self, "No File",
                                "Save the workup to a file before changing status.")
            return

        output_dir = self._source_xlsx.parent

        try:
            with db_connection(self._path) as conn:
                if lock:
                    import datetime as _dt
                    now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    conn.execute(
                        "UPDATE job SET finalized_at = ?, finalized_by = ? WHERE job_id = ?",
                        (now, self._performed_by, self._job["job_id"]),
                    )
                updated_job, new_path = transition_workup_status(
                    conn,
                    job=self._job,
                    new_status=new_status,
                    output_dir=output_dir,
                    performed_by=self._performed_by,
                )
        except Exception as exc:
            QMessageBox.critical(self, "Transition Error", f"Failed:\n{exc}")
            return

        old_path = self._source_xlsx
        self._source_xlsx = new_path
        self._job = get_job(self._path)
        self._refresh_status_display()
        self._refresh_audit_log()
        self.statusBar().showMessage(str(new_path))

        # Offer to delete the old file so the folder stays tidy
        if old_path != new_path and old_path.exists():
            reply = QMessageBox.question(
                self, "Clean Up?",
                f"Status saved to:\n{new_path.name}\n\n"
                f"Delete the previous version?\n{old_path.name}",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                try:
                    old_path.unlink()
                except Exception:
                    pass

    # ── Import TB ────────────────────────────────────────────────────────

    def _on_import_tb(self):
        from atbworkup.db.connection import db_connection

        # Check if accounts already exist → offer reimport
        with db_connection(self._path) as conn:
            existing_count = conn.execute(
                "SELECT COUNT(*) FROM accounts WHERE job_id = ?",
                (self._job["job_id"],),
            ).fetchone()[0]

        if existing_count > 0:
            reply = QMessageBox.question(
                self, "Reimport Trial Balance",
                f"This workup already has {existing_count} accounts.\n\n"
                "Reimporting will UPDATE existing PBC balances to match the new TB.\n"
                "Journal entries and tax line mappings are preserved.\n"
                "Accounts missing from the new TB will be flagged.\n\n"
                "Proceed with reimport?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
            self._do_reimport_tb()
        else:
            self._do_fresh_import_tb()

    def _do_fresh_import_tb(self):
        from atbworkup.ui.tb_import_wizard import TBImportWizard
        from atbworkup.importer.tb_writer import write_accounts
        from atbworkup.db.connection import db_connection

        initial_dir = self._job.get("workpaper_folder") or ""
        wiz = TBImportWizard(self, initial_dir=initial_dir)
        if wiz.exec() != TBImportWizard.Accepted:
            return

        result = wiz.result_data()
        if result is None or not result.accounts:
            return

        try:
            with db_connection(self._path) as conn:
                count = write_accounts(
                    conn,
                    job_id=self._job["job_id"],
                    result=result,
                    performed_by=self._performed_by,
                )
        except Exception as exc:
            QMessageBox.critical(self, "Import Error", f"Failed to write accounts:\n{exc}")
            return

        from atbworkup.models.job import get_job
        self._job = get_job(self._path)
        self._refresh_status_display()
        self._rebuild_fs_tab()
        self._rebuild_je_panel()
        self._rebuild_notes_dock()
        self._rebuild_report_tab()
        self._rebuild_workpapers_tab()
        self._tabs.setCurrentIndex(self._fs_tab_index)
        self._on_save()

        bal_msg = " (balanced ✓)" if result.is_balanced else " ⚠ OUT OF BALANCE"
        QMessageBox.information(
            self, "Import Complete",
            f"{count} accounts imported{bal_msg}.\n\n"
            f"Total debits:  {result.total_debits:,.2f}\n"
            f"Total credits: {result.total_credits:,.2f}",
        )
        self._open_mapping_workbench()

    def _do_reimport_tb(self):
        from atbworkup.ui.tb_import_wizard import TBImportWizard
        from atbworkup.importer.tb_writer import reimport_accounts
        from atbworkup.db.connection import db_connection

        initial_dir = self._job.get("workpaper_folder") or ""
        wiz = TBImportWizard(self, initial_dir=initial_dir)
        if wiz.exec() != TBImportWizard.Accepted:
            return

        result = wiz.result_data()
        if result is None or not result.accounts:
            return

        try:
            with db_connection(self._path) as conn:
                stats = reimport_accounts(
                    conn,
                    job_id=self._job["job_id"],
                    result=result,
                    performed_by=self._performed_by,
                )
        except Exception as exc:
            QMessageBox.critical(self, "Reimport Error", f"Failed:\n{exc}")
            return

        if self._grid:
            self._grid.refresh()
        self._reprint_report()
        self._refresh_audit_log()
        self._on_save()

        missing_note = (
            f"\n⚠  {stats.flagged} account(s) flagged as missing — "
            "review and delete or reclassify them."
        ) if stats.flagged else ""

        QMessageBox.information(
            self, "Reimport Complete",
            f"PBC balances updated:\n\n"
            f"  Updated:    {stats.updated}\n"
            f"  New accounts added: {stats.added}\n"
            f"  Unchanged:  {stats.unchanged}\n"
            f"  Flagged missing: {stats.flagged}"
            f"{missing_note}",
        )

    # ── Account editing ───────────────────────────────────────────────────

    def _on_edit_account(self):
        """Edit Account… button on Job Info tab — requires a selection in the grid."""
        if self._grid is None:
            return
        ids = self._grid.selected_account_ids()
        if not ids:
            QMessageBox.information(self, "Edit Account",
                                    "Select an account in the Trial Balance tab first.")
            return
        self._on_edit_account_by_id(ids[0])

    def _on_edit_account_by_id(self, account_id: str):
        from atbworkup.db.connection import db_connection
        from atbworkup.models.accounts import update_account

        with db_connection(self._path) as conn:
            row = conn.execute(
                "SELECT account_number, account_name, account_type, normal_balance, pbc_balance "
                "FROM accounts WHERE account_id = ?",
                (account_id,),
            ).fetchone()
        if row is None:
            return

        dlg = _EditAccountDialog(dict(row), parent=self)
        if dlg.exec() != QDialog.Accepted:
            return

        changes = dlg.changes()
        if not changes:
            return

        with db_connection(self._path) as conn:
            update_account(conn, account_id, **changes)
            from atbworkup.models.activity import log_activity
            log_activity(
                conn,
                job_id=self._job["job_id"],
                event_type="edited_account",
                description=f"Edited account {row['account_name']}: {', '.join(changes.keys())}",
                performed_by=self._performed_by,
            )

        if self._grid:
            self._grid.refresh()
        self._reprint_report()
        self._refresh_audit_log()
        # Enable the Edit Account button now that the grid is active
        self._btn_edit_account.setEnabled(True)

    def _open_mapping_workbench(self):
        from atbworkup.ui.mapping_workbench import MappingWorkbench
        dlg = MappingWorkbench(
            self._path, self._job["job_id"],
            self._job["entity_type"], self._job["prepared_by"],
            parent=self,
        )
        dlg.exec()
        if self._grid is not None:
            self._grid.refresh()
        self._reprint_report()


# ── Helper dialogs ────────────────────────────────────────────────────────────

class _EditAccountDialog(QDialog):
    """Edit editable fields on an account."""

    _TYPES = ["Asset", "Liability", "Equity", "Revenue", "Expense"]
    _NB    = ["Debit", "Credit"]

    def __init__(self, current: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Account")
        self.setMinimumWidth(380)
        self._original = current
        self._build_ui(current)

    def _build_ui(self, c: dict):
        from PySide6.QtWidgets import QFormLayout
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)

        self._num  = QLineEdit(c.get("account_number") or "")
        self._name = QLineEdit(c.get("account_name") or "")
        self._type = QComboBox()
        self._type.addItems(self._TYPES)
        if c.get("account_type") in self._TYPES:
            self._type.setCurrentText(c["account_type"])
        self._nb = QComboBox()
        self._nb.addItems(self._NB)
        if c.get("normal_balance") in self._NB:
            self._nb.setCurrentText(c["normal_balance"])
        self._pbc = QLineEdit(f"{c.get('pbc_balance', 0):.2f}")

        form.addRow("Account #:",      self._num)
        form.addRow("Account Name *:", self._name)
        form.addRow("Type:",           self._type)
        form.addRow("Normal Balance:", self._nb)
        form.addRow("PBC Balance:",    self._pbc)
        layout.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._validate)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _validate(self):
        if not self._name.text().strip():
            QMessageBox.warning(self, "Required", "Account Name is required.")
            return
        try:
            float(self._pbc.text())
        except ValueError:
            QMessageBox.warning(self, "Invalid", "PBC Balance must be a number.")
            return
        self.accept()

    def changes(self) -> dict:
        """Return only fields that changed from the original."""
        c = self._original
        out = {}
        num = self._num.text().strip() or None
        if num != (c.get("account_number") or None):
            out["account_number"] = num
        name = self._name.text().strip()
        if name != c.get("account_name"):
            out["account_name"] = name
        t = self._type.currentText()
        if t != c.get("account_type"):
            out["account_type"] = t
        nb = self._nb.currentText()
        if nb != c.get("normal_balance"):
            out["normal_balance"] = nb
        pbc = round(float(self._pbc.text()), 2)
        if abs(pbc - float(c.get("pbc_balance", 0))) > 0.005:
            out["pbc_balance"] = pbc
        return out


class _FinalizeConfirmDialog(QDialog):
    """Multi-step confirmation before locking a workup."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Finalize & Lock Workup")
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)

        warning = QLabel(
            "⚠  WARNING — This action is PERMANENT.\n\n"
            "Finalizing locks the workup. You will no longer be able to:\n"
            "  • Add or edit journal entries\n"
            "  • Change account mappings\n"
            "  • Modify any balances\n\n"
            "This cannot be undone.\n\n"
            "Type  FINALIZE  below to confirm:"
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("color: #7B1A1A; font-weight: bold;")
        layout.addWidget(warning)

        self._confirm_input = QLineEdit()
        self._confirm_input.setPlaceholderText("Type FINALIZE here")
        layout.addWidget(self._confirm_input)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self._ok_btn = btns.button(QDialogButtonBox.Ok)
        self._ok_btn.setText("Finalize & Lock")
        self._ok_btn.setStyleSheet("background:#7B1A1A;color:#FFF;font-weight:bold;")
        self._ok_btn.setEnabled(False)
        self._confirm_input.textChanged.connect(
            lambda t: self._ok_btn.setEnabled(t.strip() == "FINALIZE")
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
