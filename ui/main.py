"""Management UI entry point — launches toolbar and viewer."""
import sys, json, logging
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from ui.toolbar import ToolbarWindow

logging.basicConfig(level=logging.INFO)
STATUS_FILE = Path.home() / ".windowsmcp" / "status.json"

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("WindowsMCP Custom")
    toolbar = ToolbarWindow()
    toolbar.show()

    def update_status():
        try:
            if STATUS_FILE.exists():
                toolbar.update_status(json.loads(STATUS_FILE.read_text()))
        except Exception: pass

    timer = QTimer()
    timer.timeout.connect(update_status)
    timer.start(1000)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
