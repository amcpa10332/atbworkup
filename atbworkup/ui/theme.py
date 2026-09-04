"""
Firm brand palette and derived UI colors.

Brand colors (zbcpa.tax):
  Jet Black  #000000   primary typography
  White      #FFFFFF   backgrounds
  Rich Navy  #1A2B4C   headers, accents, reverse surfaces
  Platinum   #E5E5E5   alternating rows, subtle backgrounds
"""
from PySide6.QtGui import QColor

# ── Brand ────────────────────────────────────────────────────────────────
JET_BLACK  = QColor("#000000")
WHITE      = QColor("#FFFFFF")
RICH_NAVY  = QColor("#1A2B4C")
PLATINUM   = QColor("#E5E5E5")

# ── Derived / functional ─────────────────────────────────────────────────
# Section header rows
SECTION_BG   = RICH_NAVY
SECTION_FG   = WHITE

# Subsection (tax line) rows — platinum bg with navy text stays on-brand
SUBSECTION_BG = QColor("#D0D8E8")   # navy-tinted platinum
SUBSECTION_FG = RICH_NAVY

# Unmapped warning row
UNMAPPED_BG = QColor("#7B1A1A")     # dark red — intentionally off-brand to demand attention
UNMAPPED_FG = WHITE

# Account rows
ROW_BG_ODD  = WHITE
ROW_BG_EVEN = PLATINUM

# Text
TEXT_PRIMARY = JET_BLACK
TEXT_MUTED   = QColor("#888888")    # zero values, placeholders
TEXT_CREDIT  = QColor("#C62828")    # red for credit (negative) amounts

# Column header bar
COL_HEADER_BG = RICH_NAVY
COL_HEADER_FG = WHITE

# Selection highlight
SELECTION_BG = QColor("#C8D8F0")    # light navy tint
SELECTION_FG = JET_BLACK

# Badge / status chips
BADGE_BG = RICH_NAVY
BADGE_FG = WHITE

WARN_BADGE_BG = QColor("#C62828")
WARN_BADGE_FG = WHITE

# ── Amount formatting ────────────────────────────────────────────────────

def fmt_amount(value: float) -> str:
    """Format a signed amount for display.

    Positive (debit):  1,234.56
    Zero:              —
    Negative (credit): (1,234.56)   ← shown in TEXT_CREDIT color by caller
    """
    if value == 0:
        return "—"
    if value > 0:
        return f"{value:,.2f}"
    return f"({abs(value):,.2f})"


# ── Global stylesheet ────────────────────────────────────────────────────
# Segoe UI throughout — best native rendering on Windows.
# Letter-spacing on headers echoes the tracked sans-serif in the BTA tagline.

APP_STYLESHEET = """
* {
    font-family: "Segoe UI";
    font-size: 13px;
    color: #000000;
}

QWidget {
    background-color: #FFFFFF;
}

QMainWindow, QDialog, QWizard {
    background-color: #FFFFFF;
}

/* ── Tabs ── */
QTabWidget::pane {
    border: 1px solid #E5E5E5;
    background: #FFFFFF;
}
QTabBar::tab {
    font-family: "Segoe UI";
    font-size: 12px;
    background: #E5E5E5;
    color: #000000;
    padding: 6px 18px;
    border: 1px solid #cccccc;
    border-bottom: none;
    letter-spacing: 1px;
}
QTabBar::tab:selected {
    background: #1A2B4C;
    color: #FFFFFF;
    font-weight: bold;
}
QTabBar::tab:hover:!selected {
    background: #d0d8e8;
}

/* ── Buttons ── */
QPushButton {
    font-family: "Segoe UI";
    font-size: 12px;
    font-weight: bold;
    letter-spacing: 1px;
    background-color: #1A2B4C;
    color: #FFFFFF;
    border: none;
    padding: 6px 16px;
    border-radius: 3px;
}
QPushButton:hover    { background-color: #243d6a; }
QPushButton:pressed  { background-color: #101e33; }
QPushButton:disabled { background-color: #888888; color: #cccccc; }

/* ── Group boxes ── */
QGroupBox {
    font-family: "Segoe UI";
    font-size: 12px;
    font-weight: bold;
    letter-spacing: 1px;
    color: #1A2B4C;
    border: 1px solid #E5E5E5;
    border-radius: 4px;
    margin-top: 10px;
    padding-top: 6px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}

/* ── Inputs ── */
QLineEdit, QTextEdit, QPlainTextEdit {
    font-family: "Segoe UI";
    font-size: 13px;
    background: #FFFFFF;
    color: #000000;
    border: 1px solid #cccccc;
    border-radius: 3px;
    padding: 4px 6px;
    selection-background-color: #1A2B4C;
    selection-color: #FFFFFF;
}
QLineEdit:focus, QTextEdit:focus { border: 1px solid #1A2B4C; }

QComboBox {
    font-family: "Segoe UI";
    font-size: 13px;
    background: #FFFFFF;
    color: #000000;
    border: 1px solid #cccccc;
    border-radius: 3px;
    padding: 4px 6px;
}
QComboBox:focus { border: 1px solid #1A2B4C; }
QComboBox QAbstractItemView {
    background: #FFFFFF;
    color: #000000;
    selection-background-color: #1A2B4C;
    selection-color: #FFFFFF;
}

QSpinBox {
    font-family: "Segoe UI";
    font-size: 13px;
    background: #FFFFFF;
    color: #000000;
    border: 1px solid #cccccc;
    border-radius: 3px;
    padding: 4px 6px;
}
QSpinBox:focus { border: 1px solid #1A2B4C; }

/* ── Labels ── */
QLabel {
    font-family: "Segoe UI";
    color: #000000;
    background: transparent;
}

/* ── Status bar ── */
QStatusBar {
    font-family: "Segoe UI";
    font-size: 11px;
    background: #1A2B4C;
    color: #FFFFFF;
}

/* ── Wizard ── */
QWizard QLabel, QWizardPage QLabel {
    font-family: "Segoe UI";
    color: #000000;
}

/* ── Scrollbars ── */
QScrollBar:vertical {
    background: #E5E5E5;
    width: 10px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background: #1A2B4C;
    border-radius: 5px;
    min-height: 20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
"""
