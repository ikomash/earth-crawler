import os
import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from gui import MainWindow
from __version__ import __version__

if __name__ == "__main__":

    # Hack for Windows taskbar icon work correctly without app packing.
    try:
        from ctypes import windll  # Only exists on Windows.
        myappid = f'com.demonkik.earthcrawler.{__version__}'
        windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except ImportError:
        pass

    os.chdir(Path(__file__).parent.parent.resolve())
    app = QApplication(sys.argv)
    app.setStyle('fusion')
    app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    window = MainWindow()

    sys.exit(app.exec())
