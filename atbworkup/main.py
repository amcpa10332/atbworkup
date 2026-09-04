import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from atbworkup.ui.start_screen import StartScreen


def _icon_path() -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        # PyInstaller unpacks bundled `datas` under sys._MEIPASS, preserving
        # the destination path given in atbworkup.spec.
        return Path(meipass) / "atbworkup" / "assets" / "app_icon.png"
    # Running from source: this file is atbworkup/main.py, so assets live
    # right beside it.
    return Path(__file__).parent / "assets" / "app_icon.png"


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("TB Workup")
    app.setOrganizationName("zbcpa")
    icon_path = _icon_path()
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    from atbworkup.ui.theme import APP_STYLESHEET
    app.setStyleSheet(APP_STYLESHEET)
    from atbworkup.db.settings import ensure_settings_db
    ensure_settings_db()
    window = StartScreen()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
