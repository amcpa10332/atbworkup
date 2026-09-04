from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QMessageBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from atbworkup.models.job import create_workup
from atbworkup.ui.new_workup_dialog import NewWorkupDialog
from atbworkup.ui.workup_window import WorkupWindow


class StartScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("TB Workup")
        self.setMinimumSize(480, 340)
        self._windows: list[WorkupWindow] = []
        self._build_ui()
        self._ensure_profile()

    def _ensure_profile(self):
        try:
            from atbworkup.db.settings import has_profile, save_profile
            if not has_profile():
                from atbworkup.ui.first_launch_dialog import FirstLaunchDialog
                dlg = FirstLaunchDialog(self)
                dlg.exec()
                if dlg.result() == FirstLaunchDialog.Accepted:
                    save_profile(dlg.display_name(), dlg.initials())
        except Exception:
            pass

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(12)

        title = QLabel("TB Workup")
        font = QFont()
        font.setPointSize(22)
        font.setBold(True)
        title.setFont(font)
        title.setAlignment(Qt.AlignCenter)

        subtitle = QLabel("Trial Balance Workup Tool")
        subtitle.setAlignment(Qt.AlignCenter)

        btn_new  = QPushButton("Create New Workup")
        btn_open = QPushButton("Open Existing Workup")

        for btn in (btn_new, btn_open):
            btn.setFixedWidth(240)
            btn.setFixedHeight(44)
            btn.setStyleSheet(
                "QPushButton { background: #1A2B4C; color: #FFFFFF; font-weight: bold; "
                "font-size: 13px; border-radius: 4px; }"
                "QPushButton:hover { background: #2A3B6C; }"
            )

        btn_new.clicked.connect(self._on_new)
        btn_open.clicked.connect(self._on_open)

        # Secondary actions
        btn_rollforward  = QPushButton("Rollforward from Prior Year…")
        btn_consolidated = QPushButton("New Consolidated Binder…")
        btn_templates    = QPushButton("Manage Tax Line Templates…")

        for btn in (btn_rollforward, btn_consolidated, btn_templates):
            btn.setFixedWidth(240)
            btn.setFixedHeight(32)
            btn.setStyleSheet(
                "QPushButton { background: transparent; color: #1A2B4C; "
                "font-size: 11px; border: 1px solid #1A2B4C; border-radius: 3px; }"
                "QPushButton:hover { background: #E8ECF4; }"
            )

        btn_rollforward.clicked.connect(self._on_rollforward)
        btn_consolidated.clicked.connect(self._on_new_consolidated)
        btn_templates.clicked.connect(self._on_manage_templates)

        layout.addStretch()
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(28)
        layout.addWidget(btn_new,          alignment=Qt.AlignCenter)
        layout.addWidget(btn_open,         alignment=Qt.AlignCenter)
        layout.addSpacing(12)
        layout.addWidget(btn_rollforward,  alignment=Qt.AlignCenter)
        layout.addWidget(btn_consolidated, alignment=Qt.AlignCenter)
        layout.addWidget(btn_templates,    alignment=Qt.AlignCenter)
        layout.addStretch()

    # ── Handlers ──────────────────────────────────────────────────────────

    def _on_new(self):
        dlg = NewWorkupDialog(self)
        if dlg.exec() != NewWorkupDialog.Accepted:
            return

        meta      = dlg.metadata()
        folder    = Path(meta["workpaper_folder"])
        xlsx_path = folder / meta["suggested_filename"]

        if xlsx_path.exists():
            reply = QMessageBox.question(
                self, "File Exists",
                f"{xlsx_path.name} already exists in that folder.\nOverwrite it?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        try:
            from atbworkup.utils.ids import new_uuid
            from atbworkup.utils.naming import temp_atbw_path
            from atbworkup.models.job import get_job
            from atbworkup.db.connection import db_connection
            from atbworkup.exporter.review_package import save_workup
            from atbworkup.db.settings import get_active_profile, set_role_for_job

            performed_by = meta["prepared_by"]
            profile = get_active_profile()
            if profile:
                performed_by = profile["display_name"]

            job_id    = new_uuid()
            temp_path = temp_atbw_path(job_id)

            create_workup(temp_path, meta, job_id=job_id)
            job = get_job(temp_path)
            set_role_for_job(job_id, "preparer")

            with db_connection(temp_path) as conn:
                save_workup(conn, job=job, output_path=xlsx_path,
                            performed_by=performed_by)

            self._open_window(temp_path, job, source_xlsx=xlsx_path,
                              role="preparer", performed_by=performed_by)
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Could not create workup:\n{exc}")

    def _on_open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Workup File", "",
            "TB Workup Files (*.atbr.xlsx);;All Files (*)",
        )
        if not path:
            return

        from atbworkup.db.settings import (
            get_active_profile, get_role_for_job, set_role_for_job,
        )

        profile = get_active_profile()
        if not profile:
            self._ensure_profile()
            profile = get_active_profile()

        performed_by = profile["display_name"] if profile else "Unknown"

        try:
            from atbworkup.importer.package import open_from_package
            temp_path, job = open_from_package(path, performed_by=performed_by)
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Could not open workup:\n{exc}")
            return

        job_id = job["job_id"]
        role = get_role_for_job(job_id)

        if role is None:
            from atbworkup.ui.role_dialog import RoleDialog
            rdlg = RoleDialog(job["client_name"], job["tax_year"], parent=self)
            rdlg.exec()
            role = rdlg.role() or "preparer"
            if rdlg.result() == RoleDialog.Accepted and rdlg.should_remember():
                set_role_for_job(job_id, role)

        self._open_window(temp_path, job, source_xlsx=path,
                          role=role, performed_by=performed_by)

    def _on_rollforward(self):
        from atbworkup.ui.rollforward_dialog import RollforwardDialog
        dlg = RollforwardDialog(self)
        if dlg.exec() != RollforwardDialog.Accepted:
            return

        meta       = dlg.metadata()
        prior_xlsx = dlg.prior_xlsx_path()
        folder     = Path(meta["workpaper_folder"])
        xlsx_path  = folder / meta["suggested_filename"]

        if xlsx_path.exists():
            reply = QMessageBox.question(
                self, "File Exists",
                f"{xlsx_path.name} already exists.\nOverwrite it?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        try:
            from atbworkup.utils.ids import new_uuid
            from atbworkup.utils.naming import temp_atbw_path
            from atbworkup.db.connection import db_connection
            from atbworkup.exporter.review_package import save_workup
            from atbworkup.db.settings import get_active_profile, set_role_for_job
            from atbworkup.models.rollforward import create_rollforward

            profile = get_active_profile()
            performed_by = profile["display_name"] if profile else meta["prepared_by"]

            job_id    = new_uuid()
            temp_path = temp_atbw_path(job_id)

            job = create_rollforward(
                prior_xlsx_path=prior_xlsx,
                new_atbw_path=temp_path,
                new_metadata=meta,
                performed_by=performed_by,
            )
            set_role_for_job(job_id, "preparer")

            with db_connection(temp_path) as conn:
                save_workup(conn, job=job, output_path=xlsx_path,
                            performed_by=performed_by)

            self._open_window(temp_path, job, source_xlsx=xlsx_path,
                              role="preparer", performed_by=performed_by)

        except Exception as exc:
            QMessageBox.critical(self, "Rollforward Error",
                                 f"Could not create rollforward:\n{exc}")

    def _on_new_consolidated(self):
        from atbworkup.ui.new_workup_dialog import NewWorkupDialog
        dlg = NewWorkupDialog(self, force_entity_type="Consolidated")
        if dlg.exec() != NewWorkupDialog.Accepted:
            return

        meta      = dlg.metadata()
        folder    = Path(meta["workpaper_folder"])
        xlsx_path = folder / meta["suggested_filename"]

        if xlsx_path.exists():
            reply = QMessageBox.question(
                self, "File Exists",
                f"{xlsx_path.name} already exists.\nOverwrite it?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        try:
            from atbworkup.utils.ids import new_uuid
            from atbworkup.utils.naming import temp_atbw_path
            from atbworkup.models.job import get_job
            from atbworkup.db.connection import db_connection
            from atbworkup.exporter.review_package import save_workup
            from atbworkup.db.settings import get_active_profile
            from atbworkup.ui.consolidation_window import ConsolidationWindow

            profile      = get_active_profile()
            performed_by = profile["display_name"] if profile else meta["prepared_by"]
            job_id       = new_uuid()
            temp_path    = temp_atbw_path(job_id)

            from atbworkup.models.job import create_workup
            create_workup(temp_path, meta, job_id=job_id)
            job = get_job(temp_path)

            with db_connection(temp_path) as conn:
                save_workup(conn, job=job, output_path=xlsx_path,
                            performed_by=performed_by)

            win = ConsolidationWindow(
                temp_path, job, source_xlsx=xlsx_path, performed_by=performed_by
            )
            self._windows.append(win)
            win.show()
            self.close()
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Could not create consolidated binder:\n{exc}")

    def _on_manage_templates(self):
        from atbworkup.ui.template_manager import TemplateManagerDialog
        dlg = TemplateManagerDialog(self)
        dlg.exec()

    def _open_window(self, temp_path: Path, job: dict,
                     source_xlsx: str | Path,
                     role: str = "preparer",
                     performed_by: str | None = None):
        if job.get("entity_type") == "Consolidated":
            from atbworkup.ui.consolidation_window import ConsolidationWindow
            win = ConsolidationWindow(
                temp_path, job, source_xlsx=source_xlsx, performed_by=performed_by
            )
        else:
            win = WorkupWindow(temp_path, job, source_xlsx=source_xlsx,
                               role=role, performed_by=performed_by)
        self._windows.append(win)
        win.show()
        # The launcher's job is done once a company window is open — close
        # it rather than leaving it behind (show the new window first so
        # the app never briefly has zero visible top-level windows).
        self.close()
