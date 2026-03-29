"""Production-grade tests for windowspc_mcp.display.identity.

File-system operations are isolated with tmp_path / monkeypatch.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from windowspc_mcp.display.identity import (
    PersistedDisplayState,
    save_state,
    load_state,
    clear_state,
    STATE_DIR,
    STATE_FILE,
)


@pytest.fixture()
def isolated_state(tmp_path, monkeypatch):
    """Redirect STATE_DIR and STATE_FILE to a temp directory."""
    state_dir = tmp_path / ".windowsmcp"
    state_file = state_dir / "display-state.json"
    monkeypatch.setattr("windowspc_mcp.display.identity.STATE_DIR", state_dir)
    monkeypatch.setattr("windowspc_mcp.display.identity.STATE_FILE", state_file)
    return state_dir, state_file


# =========================================================================
# PersistedDisplayState
# =========================================================================


class TestPersistedDisplayState:
    """PersistedDisplayState dataclass basics."""

    def test_creation(self):
        state = PersistedDisplayState(
            device_name=r"\\.\DISPLAY3",
            display_index=2,
            width=1920,
            height=1080,
            created_at="2025-01-01T00:00:00Z",
        )
        assert state.device_name == r"\\.\DISPLAY3"
        assert state.display_index == 2
        assert state.width == 1920
        assert state.height == 1080
        assert state.created_at == "2025-01-01T00:00:00Z"

    def test_equality(self):
        a = PersistedDisplayState("D", 1, 800, 600, "T")
        b = PersistedDisplayState("D", 1, 800, 600, "T")
        assert a == b

    def test_inequality(self):
        a = PersistedDisplayState("D1", 1, 800, 600, "T")
        b = PersistedDisplayState("D2", 1, 800, 600, "T")
        assert a != b


# =========================================================================
# save_state
# =========================================================================


class TestSaveState:
    """save_state: writes JSON file, creates directory."""

    def test_creates_dir_and_writes_json(self, isolated_state):
        state_dir, state_file = isolated_state
        state = PersistedDisplayState(
            device_name=r"\\.\D3", display_index=0, width=1920, height=1080,
            created_at="2025-06-01T12:00:00Z",
        )
        save_state(state)

        assert state_dir.exists()
        assert state_file.exists()

        data = json.loads(state_file.read_text())
        assert data["device_name"] == r"\\.\D3"
        assert data["display_index"] == 0
        assert data["width"] == 1920
        assert data["height"] == 1080

    def test_overwrites_existing(self, isolated_state):
        state_dir, state_file = isolated_state
        state1 = PersistedDisplayState("D1", 0, 800, 600, "T1")
        state2 = PersistedDisplayState("D2", 1, 1920, 1080, "T2")
        save_state(state1)
        save_state(state2)

        data = json.loads(state_file.read_text())
        assert data["device_name"] == "D2"
        assert data["display_index"] == 1


# =========================================================================
# load_state
# =========================================================================


class TestLoadState:
    """load_state: reads JSON, handles missing/corrupt files."""

    def test_returns_state_when_file_exists(self, isolated_state):
        _, state_file = isolated_state
        state = PersistedDisplayState("D3", 2, 1920, 1080, "2025-01-01T00:00:00Z")
        save_state(state)

        loaded = load_state()
        assert loaded is not None
        assert loaded == state

    def test_returns_none_when_file_missing(self, isolated_state):
        assert load_state() is None

    def test_returns_none_on_corrupt_json(self, isolated_state):
        state_dir, state_file = isolated_state
        state_dir.mkdir(parents=True, exist_ok=True)
        state_file.write_text("not valid json!!!")
        assert load_state() is None

    def test_returns_none_on_invalid_keys(self, isolated_state):
        state_dir, state_file = isolated_state
        state_dir.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps({"unexpected_key": "value"}))
        assert load_state() is None

    def test_returns_none_on_missing_field(self, isolated_state):
        state_dir, state_file = isolated_state
        state_dir.mkdir(parents=True, exist_ok=True)
        # Missing 'created_at'
        state_file.write_text(json.dumps({
            "device_name": "D1", "display_index": 0,
            "width": 1920, "height": 1080,
        }))
        assert load_state() is None


# =========================================================================
# clear_state
# =========================================================================


class TestClearState:
    """clear_state: removes file, noop when missing."""

    def test_removes_existing_file(self, isolated_state):
        _, state_file = isolated_state
        save_state(PersistedDisplayState("D", 0, 800, 600, "T"))
        assert state_file.exists()

        clear_state()
        assert not state_file.exists()

    def test_noop_when_file_missing(self, isolated_state):
        # Should not raise
        clear_state()

    def test_idempotent(self, isolated_state):
        _, state_file = isolated_state
        save_state(PersistedDisplayState("D", 0, 800, 600, "T"))
        clear_state()
        clear_state()  # second call is noop
        assert not state_file.exists()
