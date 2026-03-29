"""Display state persistence for crash recovery."""
import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path

STATE_DIR = Path.home() / ".windowsmcp"
STATE_FILE = STATE_DIR / "display-state.json"

log = logging.getLogger(__name__)


@dataclass
class PersistedDisplayState:
    device_name: str
    display_index: int
    width: int
    height: int
    created_at: str  # ISO timestamp


def save_state(state: PersistedDisplayState):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(asdict(state), indent=2))


def load_state() -> PersistedDisplayState | None:
    if not STATE_FILE.exists():
        return None
    try:
        return PersistedDisplayState(**json.loads(STATE_FILE.read_text()))
    except Exception:
        return None


def clear_state():
    if STATE_FILE.exists():
        STATE_FILE.unlink()
