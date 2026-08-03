from __future__ import annotations

import logging
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from core import paths


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("NFS: The Run Mod Menu")
    app.setStyle("Fusion")

    app_icon = QIcon(paths.icon_path())
    app.setWindowIcon(app_icon)

    try:
        from ui.main_window import MainWindow
    except Exception:
        logging.getLogger("nfstr.gui").exception("Fatal error importing the UI layer")
        raise

    try:
        window = MainWindow()
    except Exception:
        logging.getLogger("nfstr.gui").exception("Fatal error during startup")
        raise

    window.show()
    app.exec()


if __name__ == "__main__":
    main()
