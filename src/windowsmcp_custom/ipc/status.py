"""Named pipe server for publishing status updates to the UI."""
import json, logging, threading, time
from pathlib import Path

logger = logging.getLogger(__name__)
STATUS_FILE = Path.home() / ".windowsmcp" / "status.json"

class StatusPublisher:
    """Publishes server status to a file for the UI to read."""
    def __init__(self, get_status):
        self._get_status = get_status
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self):
        STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        self._running = True
        self._thread = threading.Thread(target=self._publish_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        if STATUS_FILE.exists():
            STATUS_FILE.unlink(missing_ok=True)

    def _publish_loop(self):
        while self._running:
            try:
                status = self._get_status()
                STATUS_FILE.write_text(json.dumps(status, indent=2))
            except Exception:
                pass
            time.sleep(1.0)
