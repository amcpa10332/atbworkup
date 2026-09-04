"""
Template Manager dialog — browse, import, export, and delete tax line templates.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

try:
    from atbworkup.ui.theme import RICH_NAVY, WHITE
    _NAVY_HEX  = RICH_NAVY.name()   # e.g. "#1a2b4c"
    _WHITE_HEX = WHITE.name()
except Exception:
    _NAVY_HEX  = "#1A2B4C"
    _WHITE_HEX = "#FFFFFF"

from atbworkup.db.settings import settings_connection
from atbworkup.importer.template_importer import import_template_from_excel
from atbworkup.exporter.template_exporter import export_template_to_excel, export_blank_template

# ---------------------------------------------------------------------------
# Display names for built-in entity types
# ---------------------------------------------------------------------------
_DISPLAY_NAMES: dict[str, str] = {
    "1120S":          "Form 1120-S (S-Corporation)",
    "1065":           "Form 1065 (Partnership)",
    "1120":           "Form 1120 (C-Corporation)",
    "ScheduleC":      "Schedule C (Sole Proprietor)",
    "990":            "Form 990 (Non-Profit)",
    "1041":           "Form 1041 (Estate & Trust)",
    "TrustAccounting":"Trust / Court Accounting",
}


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class TemplateManagerDialog(QDialog):
    """Browse, import, export, and delete tax line templates."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Manage Tax Line Templates")
        self.setMinimumSize(880, 560)
        self._selected_entity_type: str | None = None
        self._selected_is_builtin: bool = True
        self._build_ui()
        self._load_templates()

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(8)

        # Title label
        title_label = QLabel("Manage Tax Line Templates")
        title_font = QFont("Segoe UI", 14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet(f"color: {_NAVY_HEX};")
        root_layout.addWidget(title_label)

        # Main splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(6)
        root_layout.addWidget(splitter, stretch=1)

        # ── Left panel ──────────────────────────────────────────────────
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        list_label = QLabel("Templates")
        list_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        left_layout.addWidget(list_label)

        self._template_list = QListWidget()
        self._template_list.setAlternatingRowColors(True)
        self._template_list.currentItemChanged.connect(self._on_template_selected)
        left_layout.addWidget(self._template_list, stretch=1)

        # Toolbar below list
        tb_widget = QWidget()
        tb_layout = QHBoxLayout(tb_widget)
        tb_layout.setContentsMargins(0, 4, 0, 0)
        tb_layout.setSpacing(6)

        self._btn_import  = QPushButton("Import Excel…")
        self._btn_export  = QPushButton("Export to Excel…")
        self._btn_blank   = QPushButton("Export Blank Template…")
        self._btn_delete  = QPushButton("Delete")

        self._btn_import.setToolTip("Import a template from an Excel (.xlsx) file")
        self._btn_export.setToolTip("Export the selected template to an Excel file")
        self._btn_blank.setToolTip("Export a blank template scaffold for creating a new template")
        self._btn_delete.setToolTip("Delete the selected custom template")

        self._btn_export.setEnabled(False)
        self._btn_delete.setEnabled(False)

        # Style delete button distinctively
        self._btn_delete.setStyleSheet(
            "QPushButton { background-color: #7B1A1A; color: #FFFFFF; }"
            "QPushButton:hover { background-color: #9e2222; }"
            "QPushButton:disabled { background-color: #888888; color: #cccccc; }"
        )

        tb_layout.addWidget(self._btn_import)
        tb_layout.addWidget(self._btn_export)
        tb_layout.addWidget(self._btn_blank)
        tb_layout.addStretch()
        tb_layout.addWidget(self._btn_delete)
        left_layout.addWidget(tb_widget)

        self._btn_import.clicked.connect(self._on_import)
        self._btn_export.clicked.connect(self._on_export)
        self._btn_blank.clicked.connect(self._on_export_blank)
        self._btn_delete.clicked.connect(self._on_delete)

        splitter.addWidget(left_widget)

        # ── Right panel ─────────────────────────────────────────────────
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        lines_label = QLabel("Template Lines")
        lines_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        right_layout.addWidget(lines_label)

        self._lines_tree = QTreeWidget()
        self._lines_tree.setColumnCount(4)
        self._lines_tree.setHeaderLabels(["Line Code", "Line Name", "Section", "Sort"])
        self._lines_tree.setAlternatingRowColors(True)
        self._lines_tree.setRootIsDecorated(True)
        self._lines_tree.header().setStretchLastSection(False)
        self._lines_tree.setColumnWidth(0, 110)
        self._lines_tree.setColumnWidth(1, 240)
        self._lines_tree.setColumnWidth(2, 180)
        self._lines_tree.setColumnWidth(3, 60)
        right_layout.addWidget(self._lines_tree, stretch=1)

        splitter.addWidget(right_widget)
        splitter.setSizes([340, 540])

        # ── Bottom close button ─────────────────────────────────────────
        btn_box = QDialogButtonBox(QDialogButtonBox.Close)
        btn_box.rejected.connect(self.reject)
        root_layout.addWidget(btn_box)

    # ── Data loading ───────────────────────────────────────────────────────

    def _load_templates(self) -> None:
        """Reload the template list from the settings DB."""
        self._template_list.blockSignals(True)
        self._template_list.clear()

        try:
            with settings_connection() as conn:
                rows = conn.execute("""
                    SELECT entity_type,
                           COALESCE(template_name, entity_type) AS display_name,
                           COALESCE(is_builtin, 1) AS is_builtin,
                           COUNT(*) AS line_count
                    FROM tax_line_templates
                    GROUP BY entity_type
                    ORDER BY COALESCE(is_builtin, 1) DESC, display_name
                """).fetchall()
        except Exception as exc:
            # is_builtin / template_name columns may not exist yet — fall back
            try:
                with settings_connection() as conn:
                    rows = conn.execute("""
                        SELECT entity_type,
                               entity_type AS display_name,
                               1 AS is_builtin,
                               COUNT(*) AS line_count
                        FROM tax_line_templates
                        GROUP BY entity_type
                        ORDER BY entity_type
                    """).fetchall()
            except Exception as exc2:
                QMessageBox.critical(self, "Database Error", str(exc2))
                self._template_list.blockSignals(False)
                return

        bold_font = QFont("Segoe UI", 10)
        bold_font.setBold(True)
        normal_font = QFont("Segoe UI", 10)

        for row in rows:
            entity_type = row["entity_type"] if hasattr(row, "__getitem__") else row[0]
            raw_name    = row["display_name"] if hasattr(row, "__getitem__") else row[1]
            is_builtin  = bool(row["is_builtin"] if hasattr(row, "__getitem__") else row[2])
            line_count  = row["line_count"] if hasattr(row, "__getitem__") else row[3]

            display_name = _DISPLAY_NAMES.get(entity_type, raw_name)
            label = f"{display_name}  ({line_count} lines)"

            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, entity_type)
            item.setData(Qt.UserRole + 1, is_builtin)

            if not is_builtin:
                item.setFont(bold_font)
            else:
                item.setFont(normal_font)

            self._template_list.addItem(item)

        self._template_list.blockSignals(False)

        # Re-select previously selected item if still present
        if self._selected_entity_type is not None:
            for i in range(self._template_list.count()):
                if self._template_list.item(i).data(Qt.UserRole) == self._selected_entity_type:
                    self._template_list.setCurrentRow(i)
                    return
        # Otherwise clear lines pane
        self._lines_tree.clear()
        self._btn_export.setEnabled(False)
        self._btn_delete.setEnabled(False)

    def _load_lines(self, entity_type: str) -> None:
        """Populate the lines tree for the selected template."""
        self._lines_tree.clear()

        try:
            with settings_connection() as conn:
                rows = conn.execute(
                    "SELECT financial_statement, section, section_sort_order, "
                    "       line_code, line_name, sort_order "
                    "FROM tax_line_templates "
                    "WHERE entity_type = ? AND is_active = 1 "
                    "ORDER BY financial_statement, section_sort_order, sort_order",
                    (entity_type,),
                ).fetchall()
        except Exception as exc:
            # Fallback without is_active filter
            try:
                with settings_connection() as conn:
                    rows = conn.execute(
                        "SELECT financial_statement, section, section_sort_order, "
                        "       line_code, line_name, sort_order "
                        "FROM tax_line_templates "
                        "WHERE entity_type = ? "
                        "ORDER BY financial_statement, section_sort_order, sort_order",
                        (entity_type,),
                    ).fetchall()
            except Exception as exc2:
                return

        if not rows:
            return

        # Group: financial_statement -> section -> lines
        from collections import defaultdict, OrderedDict

        fs_map: dict[str, list] = OrderedDict()
        for row in rows:
            row_d = dict(row)
            fs = row_d["financial_statement"]
            if fs not in fs_map:
                fs_map[fs] = []
            fs_map[fs].append(row_d)

        header_font = QFont("Segoe UI", 10)
        header_font.setBold(True)

        for fs_name, fs_rows in fs_map.items():
            fs_item = QTreeWidgetItem(self._lines_tree, [fs_name, "", "", ""])
            fs_item.setFont(0, header_font)
            fs_item.setFlags(fs_item.flags() & ~Qt.ItemIsSelectable)
            fs_item.setBackground(0, __import__("PySide6.QtGui", fromlist=["QColor"]).QColor(_NAVY_HEX))
            fs_item.setForeground(0, __import__("PySide6.QtGui", fromlist=["QColor"]).QColor(_WHITE_HEX))
            for col in range(1, 4):
                fs_item.setBackground(col, __import__("PySide6.QtGui", fromlist=["QColor"]).QColor(_NAVY_HEX))

            for row_d in fs_rows:
                line_item = QTreeWidgetItem(fs_item, [
                    row_d.get("line_code", ""),
                    row_d.get("line_name", ""),
                    row_d.get("section", ""),
                    str(row_d.get("sort_order", "")),
                ])
                fs_item.addChild(line_item)

            fs_item.setExpanded(True)

        self._lines_tree.expandAll()

    # ── Signal handlers ────────────────────────────────────────────────────

    def _on_template_selected(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            self._selected_entity_type = None
            self._btn_export.setEnabled(False)
            self._btn_delete.setEnabled(False)
            self._lines_tree.clear()
            return

        entity_type = current.data(Qt.UserRole)
        is_builtin  = bool(current.data(Qt.UserRole + 1))
        self._selected_entity_type = entity_type
        self._selected_is_builtin  = is_builtin

        self._btn_export.setEnabled(True)
        self._btn_delete.setEnabled(not is_builtin)
        self._load_lines(entity_type)

    def _on_import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Template from Excel",
            "",
            "Excel Files (*.xlsx);;All Files (*)",
        )
        if not path:
            return

        try:
            parsed = import_template_from_excel(path)
        except ValueError as exc:
            QMessageBox.critical(self, "Import Error", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self, "Import Error", f"Unexpected error:\n{exc}")
            return

        name = parsed.get("template_name", parsed.get("entity_type_code", ""))
        count = len(parsed.get("lines", []))
        QMessageBox.information(
            self,
            "Import Successful",
            f"Template '{name}' imported successfully with {count} line(s).",
        )
        self._selected_entity_type = parsed.get("entity_type_code")
        self._load_templates()

    def _on_export(self) -> None:
        if not self._selected_entity_type:
            return

        default_name = f"{self._selected_entity_type}_template.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Template to Excel",
            default_name,
            "Excel Files (*.xlsx);;All Files (*)",
        )
        if not path:
            return

        try:
            export_template_to_excel(self._selected_entity_type, path)
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", str(exc))
            return

        QMessageBox.information(
            self,
            "Export Successful",
            f"Template exported to:\n{path}",
        )

    def _on_export_blank(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Blank Template",
            "blank_template.xlsx",
            "Excel Files (*.xlsx);;All Files (*)",
        )
        if not path:
            return

        try:
            export_blank_template(path)
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", str(exc))
            return

        QMessageBox.information(
            self,
            "Export Successful",
            f"Blank template scaffold exported to:\n{path}\n\n"
            "Edit the Info sheet and replace the EXAMPLE rows, then import.",
        )

    def _on_delete(self) -> None:
        if not self._selected_entity_type or self._selected_is_builtin:
            return

        entity_type = self._selected_entity_type
        display_name = _DISPLAY_NAMES.get(entity_type, entity_type)

        confirm = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Delete template '{display_name}'?\n\n"
            "This will remove all tax line mappings for this entity type. "
            "Any existing workups that reference these lines will retain their "
            "historical mapping data, but new workups cannot use this template.\n\n"
            "This action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        try:
            with settings_connection() as conn:
                conn.execute(
                    "DELETE FROM tax_line_templates WHERE entity_type = ?",
                    (entity_type,),
                )
        except Exception as exc:
            QMessageBox.critical(self, "Delete Error", str(exc))
            return

        self._selected_entity_type = None
        self._load_templates()
