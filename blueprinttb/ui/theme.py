"""
Firm brand palette and derived UI colors.

Brand colors (zbcpa.tax):
  Jet Black  #000000   primary typography
  White      #FFFFFF   backgrounds
  Rich Navy  #1A2B4C   headers, accents, reverse surfaces
  Platinum   #E5E5E5   subtle backgrounds
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QStyledItemDelegate, QStyle, QStyleOptionViewItem

# ── Brand ────────────────────────────────────────────────────────────────
JET_BLACK  = QColor("#000000")
WHITE      = QColor("#FFFFFF")
RICH_NAVY  = QColor("#1A2B4C")
PLATINUM   = QColor("#E5E5E5")

# ── Derived / functional ─────────────────────────────────────────────────
# Section header rows (FS banner: "Balance Sheet" / "Profit & Loss") —
# orange fill, white text, per firm request: the previous navy fill read as
# too low-contrast/hard to read at a glance.
SECTION_BG   = QColor("#ED7D31")
SECTION_FG   = WHITE

# Subsection (tax line) rows and account-group rows both get the same
# platinum-family fill / black text tier, per firm request. Lighter than an
# earlier #C6C6C6 pass (too dark), but still a clear step down from plain
# white -- account rows no longer alternate (see ROW_BG_ODD/EVEN below), so
# this only needs to read as distinct from white, not from a second tint.
SUBSECTION_BG = QColor("#DADADA")
SUBSECTION_FG = JET_BLACK

# Unmapped warning row
UNMAPPED_BG = QColor("#7B1A1A")     # dark red — intentionally off-brand to demand attention
UNMAPPED_FG = WHITE

# Account rows — flat white, no alternating stripe. Alternating shading read
# as visual noise / harder to read line to line, per firm request.
ROW_BG_ODD  = WHITE
ROW_BG_EVEN = WHITE

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

# ── Item-view background fix ─────────────────────────────────────────────

class RoleBackgroundDelegate(QStyledItemDelegate):
    """Fixes a long-standing Qt limitation: once ANY QSS rule targets
    `::item` on a QTreeWidget/QTreeView (even just for padding or a
    border-bottom), Qt's CSS-based item painting silently stops honoring
    QTreeWidgetItem.setBackground() (Qt::BackgroundRole) for the item's
    normal, non-selected state -- the foreground/text color set via
    setForeground() still applies, but the fill color does not. That is
    exactly what made bold white/orange/navy header text "unreadable": the
    text color was correct, it was just sitting on the tree's plain white
    background instead of the colored fill it was designed for, and no
    amount of picking different colors fixes it -- confirmed by grabbing
    the actual rendered pixmap and reading pixel colors, which came back
    #ffffff at rows whose model data said otherwise.

    Fix: re-apply Qt::BackgroundRole as an explicit fillRect() before the
    normal paint, for every row except an actively-selected one (selection
    highlighting is already styled correctly via QSS `:selected` and should
    stay in control there).
    """

    def paint(self, painter, option, index):
        option = QStyleOptionViewItem(option)
        self.initStyleOption(option, index)
        if not (option.state & QStyle.State_Selected):
            bg = index.data(Qt.BackgroundRole)
            if bg is not None:
                painter.save()
                painter.fillRect(option.rect, bg)
                painter.restore()
        super().paint(painter, option, index)


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
