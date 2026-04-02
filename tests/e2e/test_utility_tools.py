"""E2E tests for utility tools (non-input, non-screen).

Each test builds the full stack: ServerStateManager, ConfinementEngine, ToolGuard,
AgentInputService, and registers all tools on a FastMCP instance. Win32/external
APIs are mocked at the boundary so the real guard, confinement engine, and state
machine handle every request.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import types
from dataclasses import dataclass
from typing import Optional
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from fastmcp import FastMCP

from windowspc_mcp.confinement.engine import ConfinementEngine, ScreenBounds
from windowspc_mcp.confinement.guard import ToolGuard
from windowspc_mcp.display.manager import DisplayInfo, DisplayManager
from windowspc_mcp.server import ServerStateManager, ServerState
from windowspc_mcp.tools import register_all


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _text(result) -> str:
    """Extract the text payload from a FastMCP ToolResult."""
    parts = []
    for c in result.content:
        parts.append(c.text)
    return "\n".join(parts)


def _json_list(result) -> list:
    """Extract content items from a ToolResult as list of dicts."""
    items = []
    for item in result.content:
        d = {"type": item.type}
        if hasattr(item, "text"):
            d["text"] = item.text
        if hasattr(item, "data"):
            d["data"] = item.data
        if hasattr(item, "mimeType"):
            d["mimeType"] = item.mimeType
        items.append(d)
    return items


def _call(mcp: FastMCP, name: str, args: dict | None = None):
    """Synchronously call a tool on the FastMCP instance."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Already inside an async context — should not happen in these tests
        raise RuntimeError("Cannot call _call from a running event loop")

    return asyncio.run(mcp.call_tool(name, args or {}))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

AGENT_DISPLAY = DisplayInfo(
    device_name=r"\\.\DISPLAY3",
    x=3840, y=0,
    width=1920, height=1080,
    is_agent=True,
)

MONITOR_LIST = [
    DisplayInfo(device_name=r"\\.\DISPLAY1", x=0, y=0, width=1920, height=1080),
    DisplayInfo(device_name=r"\\.\DISPLAY2", x=1920, y=0, width=1920, height=1080),
    AGENT_DISPLAY,
]


@pytest.fixture()
def stack():
    """Build the full server stack with mocked DisplayManager and register all tools."""
    state_mgr = ServerStateManager()
    confinement = ConfinementEngine()
    confinement.set_agent_bounds(AGENT_DISPLAY)

    # Mock display manager — expose a real DisplayInfo but mock Win32 enumeration
    dm = MagicMock(spec=DisplayManager)
    dm.agent_display = AGENT_DISPLAY
    dm.enumerate_monitors.return_value = list(MONITOR_LIST)
    dm.is_ready = True
    dm._latest_tree_state = None

    guard = ToolGuard(state_mgr, confinement)

    # Build a lightweight mock input service
    input_svc = MagicMock()
    input_svc.click.return_value = "Clicked"
    input_svc.type_text.return_value = "Typed"
    input_svc.scroll.return_value = "Scrolled"
    input_svc.move.return_value = "Moved"

    mcp = FastMCP("test-utility-tools")

    register_all(
        mcp,
        get_display_manager=lambda: dm,
        get_confinement=lambda: confinement,
        get_state_manager=lambda: state_mgr,
        get_guard=lambda: guard,
        get_input_service=lambda: input_svc,
    )

    # Transition to READY so that guarded tools pass
    state_mgr.transition(ServerState.READY)

    return types.SimpleNamespace(
        mcp=mcp,
        state_mgr=state_mgr,
        confinement=confinement,
        dm=dm,
        guard=guard,
        input_svc=input_svc,
    )


# ===================================================================
# 1. Clipboard
# ===================================================================

class TestClipboardE2E:
    """Clipboard tool E2E — mocks win32clipboard at the import boundary."""

    def test_get_clipboard_content(self, stack):
        mock_clipboard = MagicMock()
        mock_con = MagicMock()
        mock_con.CF_UNICODETEXT = 13
        mock_clipboard.IsClipboardFormatAvailable.return_value = True
        mock_clipboard.GetClipboardData.return_value = "hello world"

        with patch.dict("sys.modules", {
            "win32clipboard": mock_clipboard,
            "win32con": mock_con,
        }):
            result = _call(stack.mcp, "Clipboard", {"action": "get"})
        text = _text(result)
        assert "hello world" in text

    def test_set_clipboard_content(self, stack):
        mock_clipboard = MagicMock()
        mock_con = MagicMock()
        mock_con.CF_UNICODETEXT = 13

        with patch.dict("sys.modules", {
            "win32clipboard": mock_clipboard,
            "win32con": mock_con,
        }):
            result = _call(stack.mcp, "Clipboard", {"action": "set", "content": "foo bar"})
        text = _text(result)
        assert "7 character" in text
        mock_clipboard.SetClipboardData.assert_called_once_with(13, "foo bar")

    def test_get_empty_clipboard(self, stack):
        mock_clipboard = MagicMock()
        mock_con = MagicMock()
        mock_con.CF_UNICODETEXT = 13
        mock_clipboard.IsClipboardFormatAvailable.return_value = True
        mock_clipboard.GetClipboardData.return_value = ""

        with patch.dict("sys.modules", {
            "win32clipboard": mock_clipboard,
            "win32con": mock_con,
        }):
            result = _call(stack.mcp, "Clipboard", {"action": "get"})
        text = _text(result)
        assert "empty clipboard" in text.lower()

    def test_clipboard_no_text_format(self, stack):
        mock_clipboard = MagicMock()
        mock_con = MagicMock()
        mock_con.CF_UNICODETEXT = 13
        mock_clipboard.IsClipboardFormatAvailable.return_value = False

        with patch.dict("sys.modules", {
            "win32clipboard": mock_clipboard,
            "win32con": mock_con,
        }):
            result = _call(stack.mcp, "Clipboard", {"action": "get"})
        text = _text(result)
        assert "does not contain text" in text.lower()

    def test_clipboard_unknown_action(self, stack):
        mock_clipboard = MagicMock()
        mock_con = MagicMock()
        mock_con.CF_UNICODETEXT = 13

        with patch.dict("sys.modules", {
            "win32clipboard": mock_clipboard,
            "win32con": mock_con,
        }):
            result = _call(stack.mcp, "Clipboard", {"action": "delete"})
        text = _text(result)
        assert "unknown action" in text.lower()

    def test_clipboard_set_missing_content(self, stack):
        mock_clipboard = MagicMock()
        mock_con = MagicMock()
        mock_con.CF_UNICODETEXT = 13

        with patch.dict("sys.modules", {
            "win32clipboard": mock_clipboard,
            "win32con": mock_con,
        }):
            result = _call(stack.mcp, "Clipboard", {"action": "set"})
        text = _text(result)
        assert "content" in text.lower() and "required" in text.lower()


# ===================================================================
# 2. PowerShell
# ===================================================================

class TestPowerShellE2E:
    """PowerShell tool E2E — mocks subprocess.run."""

    def test_execute_returns_stdout(self, stack):
        fake = subprocess.CompletedProcess(args=[], returncode=0, stdout="OK\n", stderr="")
        with patch("subprocess.run", return_value=fake):
            result = _call(stack.mcp, "PowerShell", {"command": "echo OK"})
        assert "OK" in _text(result)

    def test_command_with_stderr(self, stack):
        fake = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="bad command\n")
        with patch("subprocess.run", return_value=fake):
            result = _call(stack.mcp, "PowerShell", {"command": "bad"})
        text = _text(result)
        assert "stderr" in text.lower() or "bad command" in text

    def test_stdout_plus_stderr(self, stack):
        fake = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="data\n", stderr="warn\n"
        )
        with patch("subprocess.run", return_value=fake):
            result = _call(stack.mcp, "PowerShell", {"command": "mixed"})
        text = _text(result)
        assert "data" in text
        assert "warn" in text

    def test_timeout_handling(self, stack):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 5)):
            result = _call(stack.mcp, "PowerShell", {"command": "hang", "timeout": 5})
        text = _text(result)
        assert "timed out" in text.lower()

    def test_timeout_clamped_low(self, stack):
        """Timeout < 1 should be clamped to 1."""
        fake = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr="")
        with patch("subprocess.run", return_value=fake) as mock_run:
            _call(stack.mcp, "PowerShell", {"command": "x", "timeout": -10})
        # The timeout kwarg passed to subprocess.run should be 1
        _, kwargs = mock_run.call_args
        assert kwargs["timeout"] == 1

    def test_timeout_clamped_high(self, stack):
        """Timeout > 120 should be clamped to 120."""
        fake = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr="")
        with patch("subprocess.run", return_value=fake) as mock_run:
            _call(stack.mcp, "PowerShell", {"command": "x", "timeout": 9999})
        _, kwargs = mock_run.call_args
        assert kwargs["timeout"] == 120

    def test_no_output(self, stack):
        fake = subprocess.CompletedProcess(args=[], returncode=42, stdout="", stderr="")
        with patch("subprocess.run", return_value=fake):
            result = _call(stack.mcp, "PowerShell", {"command": "noop"})
        text = _text(result)
        assert "exit code 42" in text


# ===================================================================
# 3. App
# ===================================================================

class TestAppE2E:
    """App tool E2E — mocks subprocess.Popen, psutil, and uia.controls."""

    def _app_patches(self):
        """Common patch set for the App tool."""
        mock_proc = MagicMock()
        mock_proc.pid = 1234
        mock_proc.children.return_value = []

        mock_psutil_process = MagicMock(return_value=mock_proc)

        return {
            "popen": patch("subprocess.Popen", return_value=MagicMock(pid=1234)),
            "psutil_process": patch("psutil.Process", mock_psutil_process),
            "enum_windows": patch(
                "windowspc_mcp.uia.controls.enumerate_windows", return_value=[100]
            ),
            "is_visible": patch(
                "windowspc_mcp.uia.controls.is_window_visible", return_value=True
            ),
            "get_pid": patch(
                "windowspc_mcp.uia.controls.get_window_pid", return_value=1234
            ),
            "get_rect": patch(
                "windowspc_mcp.uia.controls.get_window_rect",
                return_value=(3840, 0, 4200, 400),
            ),
            "move": patch("windowspc_mcp.uia.controls.move_window"),
            "sleep": patch("time.sleep"),
        }

    def test_launch_moves_windows(self, stack):
        patches = self._app_patches()
        with (
            patches["popen"],
            patches["psutil_process"],
            patches["enum_windows"],
            patches["is_visible"],
            patches["get_pid"],
            patches["get_rect"],
            patches["move"] as mock_move,
            patches["sleep"],
        ):
            result = _call(stack.mcp, "App", {"name": "notepad"})
        text = _text(result)
        assert "notepad" in text.lower()
        assert "PID 1234" in text
        # Window should have been moved at least once
        assert mock_move.called

    def test_launch_with_args(self, stack):
        patches = self._app_patches()
        with (
            patches["popen"] as mock_popen,
            patches["psutil_process"],
            patches["enum_windows"],
            patches["is_visible"],
            patches["get_pid"],
            patches["get_rect"],
            patches["move"],
            patches["sleep"],
        ):
            _call(stack.mcp, "App", {"name": "code", "args": ["--new-window"]})
        cmd_arg = mock_popen.call_args[0][0]
        assert "--new-window" in cmd_arg

    def test_launch_with_url(self, stack):
        patches = self._app_patches()
        with (
            patches["popen"] as mock_popen,
            patches["psutil_process"],
            patches["enum_windows"],
            patches["is_visible"],
            patches["get_pid"],
            patches["get_rect"],
            patches["move"],
            patches["sleep"],
        ):
            _call(stack.mcp, "App", {"name": "chrome", "url": "https://example.com"})
        cmd_arg = mock_popen.call_args[0][0]
        assert "https://example.com" in cmd_arg

    def test_guard_blocks_in_non_ready_state(self, stack):
        stack.state_mgr.transition(
            ServerState.DEGRADED, reason="display lost"
        )
        result = _call(stack.mcp, "App", {"name": "notepad"})
        text = _text(result)
        assert "cannot use" in text.lower() or "degraded" in text.lower()


# ===================================================================
# 4. Screenshot
# ===================================================================

class TestScreenshotE2E:
    """Screenshot tool E2E — mocks display.capture."""

    def _capture_patches(self):
        """Create patches for the capture subsystem."""
        from PIL import Image

        fake_image = Image.new("RGB", (100, 100), color="red")
        return {
            "capture": patch(
                "windowspc_mcp.display.capture.capture_region", return_value=fake_image
            ),
            "b64": patch(
                "windowspc_mcp.display.capture.image_to_base64",
                return_value="data:image/jpeg;base64,AAAA",
            ),
        }

    def test_capture_agent_screen(self, stack):
        p = self._capture_patches()
        with p["capture"] as cap, p["b64"]:
            result = _call(stack.mcp, "Screenshot", {"screen": "agent"})
        data = _json_list(result)
        assert len(data) >= 2
        # Should have an image entry
        assert any(d.get("type") == "image" for d in data)
        # capture_region was called with agent bounds
        cap.assert_called_once_with(3840, 0, 5760, 1080)

    def test_capture_all_screens(self, stack):
        p = self._capture_patches()
        with p["capture"] as cap, p["b64"]:
            result = _call(stack.mcp, "Screenshot", {"screen": "all"})
        data = _json_list(result)
        images = [d for d in data if d.get("type") == "image"]
        assert len(images) == 3  # 3 monitors
        assert cap.call_count == 3

    def test_capture_by_index(self, stack):
        p = self._capture_patches()
        with p["capture"] as cap, p["b64"]:
            result = _call(stack.mcp, "Screenshot", {"screen": "1"})
        data = _json_list(result)
        assert any(d.get("type") == "image" for d in data)
        # Monitor index 1 is DISPLAY2 at (1920,0) -> (3840,1080)
        cap.assert_called_once_with(1920, 0, 3840, 1080)

    def test_capture_bad_index(self, stack):
        p = self._capture_patches()
        with p["capture"], p["b64"]:
            result = _call(stack.mcp, "Screenshot", {"screen": "99"})
        data = _json_list(result)
        assert any("out of range" in d.get("text", "") for d in data)

    def test_guard_blocks_in_recovering_state(self, stack):
        stack.state_mgr.transition(ServerState.RECOVERING)
        result = _call(stack.mcp, "Screenshot", {"screen": "agent"})
        text = _text(result)
        assert "cannot use" in text.lower() or "recovering" in text.lower()


# ===================================================================
# 5. Snapshot
# ===================================================================

class TestSnapshotE2E:
    """Snapshot tool E2E — mocks capture + uia.controls + tree service."""

    def _snapshot_patches(self):
        from PIL import Image
        from windowspc_mcp.tree.views import TreeState, TreeElementNode, ScrollElementNode, BoundingBox

        fake_image = Image.new("RGB", (100, 100), color="blue")
        fake_tree = TreeState(
            interactive_nodes=[
                TreeElementNode(
                    name="OK",
                    control_type="Button",
                    bounding_box=BoundingBox(left=3900, top=100, right=3950, bottom=130),
                    window_name="TestApp",
                    metadata={"has_focused": False},
                ),
            ],
            scrollable_nodes=[
                ScrollElementNode(
                    name="ContentArea",
                    control_type="Document",
                    bounding_box=BoundingBox(left=3840, top=0, right=5760, bottom=1080),
                    window_name="TestApp",
                    metadata={"vertical_scrollable": True, "vertical_scroll_percent": 0},
                ),
            ],
        )

        return {
            "capture": patch(
                "windowspc_mcp.display.capture.capture_region", return_value=fake_image
            ),
            "b64": patch(
                "windowspc_mcp.display.capture.image_to_base64",
                return_value="data:image/jpeg;base64,BBBB",
            ),
            "enum_windows": patch(
                "windowspc_mcp.uia.controls.enumerate_windows", return_value=[200]
            ),
            "is_visible": patch(
                "windowspc_mcp.uia.controls.is_window_visible", return_value=True
            ),
            "get_rect": patch(
                "windowspc_mcp.uia.controls.get_window_rect",
                return_value=(3840, 0, 5760, 1080),
            ),
            "get_title": patch(
                "windowspc_mcp.uia.controls.get_window_title",
                return_value="TestApp",
            ),
            "get_class": patch(
                "windowspc_mcp.uia.controls.get_window_class",
                return_value="ApplicationFrameWindow",
            ),
            "tree_service": patch(
                "windowspc_mcp.tree.service.TreeService",
            ),
            "fake_tree": fake_tree,
        }

    def test_snapshot_returns_image_and_tree(self, stack):
        p = self._snapshot_patches()
        mock_tree_cls = p["tree_service"]

        with (
            p["capture"],
            p["b64"],
            p["enum_windows"],
            p["is_visible"],
            p["get_rect"],
            p["get_title"],
            p["get_class"],
            mock_tree_cls as ts_cls,
        ):
            ts_cls.return_value.get_state.return_value = p["fake_tree"]
            result = _call(stack.mcp, "Snapshot", {"screen": "agent"})

        data = _json_list(result)
        # Should have image + description + windows/elements text
        assert len(data) >= 3
        assert any(d.get("type") == "image" for d in data)
        # The text sections should mention interactive elements
        text_items = [d.get("text", "") for d in data if d.get("type") == "text"]
        full_text = " ".join(text_items)
        assert "Interactive" in full_text
        assert "Scrollable" in full_text

    def test_snapshot_stores_tree_state(self, stack):
        p = self._snapshot_patches()
        with (
            p["capture"],
            p["b64"],
            p["enum_windows"],
            p["is_visible"],
            p["get_rect"],
            p["get_title"],
            p["get_class"],
            p["tree_service"] as ts_cls,
        ):
            ts_cls.return_value.get_state.return_value = p["fake_tree"]
            _call(stack.mcp, "Snapshot", {"screen": "agent"})

        # The display manager should have _latest_tree_state set
        stored = stack.dm._latest_tree_state
        assert stored is not None
        assert len(stored.interactive_nodes) == 1
        assert stored.interactive_nodes[0].name == "OK"

    def test_snapshot_no_agent_screen(self, stack):
        stack.dm.agent_display = None
        p = self._snapshot_patches()
        with (
            p["capture"],
            p["b64"],
            p["enum_windows"],
            p["is_visible"],
            p["get_rect"],
            p["get_title"],
            p["get_class"],
            p["tree_service"] as ts_cls,
        ):
            ts_cls.return_value.get_state.return_value = p["fake_tree"]
            result = _call(stack.mcp, "Snapshot", {"screen": "agent"})

        data = _json_list(result)
        full_text = " ".join(d.get("text", "") for d in data)
        assert "error" in full_text.lower() or "no agent screen" in full_text.lower()


# ===================================================================
# 6. Notification
# ===================================================================

class TestNotificationE2E:
    """Notification tool E2E — mocks subprocess.run."""

    def test_sends_notification(self, stack):
        fake = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with patch("subprocess.run", return_value=fake):
            result = _call(stack.mcp, "Notification", {
                "title": "Test Title",
                "message": "Test body",
            })
        text = _text(result)
        assert "notification sent" in text.lower()
        assert "Test Title" in text

    def test_notification_with_warning(self, stack):
        fake = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="warning text"
        )
        with patch("subprocess.run", return_value=fake):
            result = _call(stack.mcp, "Notification", {
                "title": "Warn",
                "message": "body",
            })
        text = _text(result)
        assert "warning" in text.lower()

    def test_notification_timeout(self, stack):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 15)):
            result = _call(stack.mcp, "Notification", {
                "title": "Slow",
                "message": "body",
            })
        text = _text(result)
        assert "timed out" in text.lower()


# ===================================================================
# 7. Process
# ===================================================================

class TestProcessE2E:
    """Process tool E2E — mocks psutil."""

    def _make_proc_info(self, pid, name, status, rss_mb):
        mem = MagicMock()
        mem.rss = int(rss_mb * 1024 * 1024)
        info = {"pid": pid, "name": name, "status": status, "memory_info": mem}
        proc = MagicMock()
        proc.info = info
        return proc

    def test_list_processes(self, stack):
        procs = [
            self._make_proc_info(100, "notepad.exe", "running", 12.5),
            self._make_proc_info(200, "chrome.exe", "running", 300.0),
        ]
        with patch("psutil.process_iter", return_value=procs):
            result = _call(stack.mcp, "Process", {"action": "list"})
        text = _text(result)
        assert "notepad.exe" in text
        assert "chrome.exe" in text

    def test_list_processes_filtered(self, stack):
        procs = [
            self._make_proc_info(100, "notepad.exe", "running", 12.5),
            self._make_proc_info(200, "chrome.exe", "running", 300.0),
        ]
        with patch("psutil.process_iter", return_value=procs):
            result = _call(stack.mcp, "Process", {"action": "list", "name": "chrome"})
        text = _text(result)
        assert "chrome.exe" in text
        assert "notepad.exe" not in text

    def test_kill_by_pid(self, stack):
        mock_proc = MagicMock()
        mock_proc.name.return_value = "notepad.exe"
        with patch("psutil.Process", return_value=mock_proc):
            result = _call(stack.mcp, "Process", {"action": "kill", "pid": 100})
        text = _text(result)
        assert "terminated" in text.lower()
        assert "notepad.exe" in text
        mock_proc.terminate.assert_called_once()

    def test_kill_requires_target(self, stack):
        result = _call(stack.mcp, "Process", {"action": "kill"})
        text = _text(result)
        assert "provide" in text.lower() or "error" in text.lower()

    def test_kill_nonexistent_pid(self, stack):
        import psutil
        with patch("psutil.Process", side_effect=psutil.NoSuchProcess(pid=9999)):
            result = _call(stack.mcp, "Process", {"action": "kill", "pid": 9999})
        text = _text(result)
        assert "no process" in text.lower() or "error" in text.lower()

    def test_unknown_action(self, stack):
        result = _call(stack.mcp, "Process", {"action": "restart"})
        text = _text(result)
        assert "unknown action" in text.lower()


# ===================================================================
# 8. FileSystem
# ===================================================================

class TestFileSystemE2E:
    """FileSystem tool E2E — uses real temp files."""

    def test_write_and_read(self, stack, tmp_path):
        fpath = str(tmp_path / "test.txt")
        # Write
        result = _call(stack.mcp, "FileSystem", {
            "action": "write",
            "path": fpath,
            "content": "hello world",
        })
        text = _text(result)
        assert "11 character" in text

        # Read back
        result = _call(stack.mcp, "FileSystem", {"action": "read", "path": fpath})
        text = _text(result)
        assert "hello world" in text

    def test_list_directory(self, stack, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        (tmp_path / "subdir").mkdir()

        result = _call(stack.mcp, "FileSystem", {"action": "list", "path": str(tmp_path)})
        text = _text(result)
        assert "a.txt" in text
        assert "b.txt" in text
        assert "subdir/" in text

    def test_info(self, stack, tmp_path):
        fpath = tmp_path / "data.bin"
        fpath.write_bytes(b"12345")
        result = _call(stack.mcp, "FileSystem", {"action": "info", "path": str(fpath)})
        text = _text(result)
        assert "5 bytes" in text
        assert "file" in text.lower()

    def test_copy(self, stack, tmp_path):
        src = tmp_path / "src.txt"
        src.write_text("content")
        dst = str(tmp_path / "dst.txt")
        result = _call(stack.mcp, "FileSystem", {
            "action": "copy", "path": str(src), "destination": dst,
        })
        text = _text(result)
        assert "copied" in text.lower()
        assert (tmp_path / "dst.txt").read_text() == "content"

    def test_move(self, stack, tmp_path):
        src = tmp_path / "move_me.txt"
        src.write_text("data")
        dst = str(tmp_path / "moved.txt")
        result = _call(stack.mcp, "FileSystem", {
            "action": "move", "path": str(src), "destination": dst,
        })
        text = _text(result)
        assert "moved" in text.lower()
        assert not src.exists()
        assert (tmp_path / "moved.txt").read_text() == "data"

    def test_delete_file(self, stack, tmp_path):
        fpath = tmp_path / "del.txt"
        fpath.write_text("bye")
        result = _call(stack.mcp, "FileSystem", {"action": "delete", "path": str(fpath)})
        text = _text(result)
        assert "deleted" in text.lower()
        assert not fpath.exists()

    def test_read_nonexistent(self, stack):
        result = _call(stack.mcp, "FileSystem", {
            "action": "read", "path": r"C:\nonexistent_path_abc123\no.txt",
        })
        text = _text(result)
        assert "not found" in text.lower() or "error" in text.lower()

    def test_write_missing_content(self, stack, tmp_path):
        fpath = str(tmp_path / "empty.txt")
        result = _call(stack.mcp, "FileSystem", {"action": "write", "path": fpath})
        text = _text(result)
        assert "content" in text.lower() and "required" in text.lower()

    def test_unknown_action(self, stack, tmp_path):
        result = _call(stack.mcp, "FileSystem", {
            "action": "compress", "path": str(tmp_path),
        })
        text = _text(result)
        assert "unknown action" in text.lower()


# ===================================================================
# 9. Registry
# ===================================================================

class TestRegistryE2E:
    """Registry tool E2E — mocks winreg at the import boundary."""

    def _make_winreg(self):
        m = MagicMock()
        m.HKEY_LOCAL_MACHINE = 0x80000002
        m.HKEY_CURRENT_USER = 0x80000001
        m.HKEY_CLASSES_ROOT = 0x80000000
        m.HKEY_USERS = 0x80000003
        m.HKEY_CURRENT_CONFIG = 0x80000005
        m.KEY_READ = 0x20019
        m.KEY_SET_VALUE = 0x0002
        m.KEY_CREATE_SUB_KEY = 0x0004
        m.REG_SZ = 1
        m.REG_DWORD = 4
        m.REG_QWORD = 11
        m.REG_BINARY = 3
        m.REG_EXPAND_SZ = 2
        m.REG_MULTI_SZ = 7
        return m

    def test_read_value(self, stack):
        mock_winreg = self._make_winreg()
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value.__enter__ = MagicMock(return_value=mock_key)
        mock_winreg.OpenKey.return_value.__exit__ = MagicMock(return_value=False)
        mock_winreg.QueryValueEx.return_value = ("hello", 1)  # REG_SZ = 1

        with patch.dict("sys.modules", {"winreg": mock_winreg}):
            result = _call(stack.mcp, "Registry", {
                "action": "read",
                "key": r"HKCU\Software\Test",
                "name": "MyValue",
            })
        text = _text(result)
        assert "MyValue" in text
        assert "hello" in text

    def test_write_value(self, stack):
        mock_winreg = self._make_winreg()
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value.__enter__ = MagicMock(return_value=mock_key)
        mock_winreg.OpenKey.return_value.__exit__ = MagicMock(return_value=False)

        with patch.dict("sys.modules", {"winreg": mock_winreg}):
            result = _call(stack.mcp, "Registry", {
                "action": "write",
                "key": r"HKCU\Software\Test",
                "name": "NewVal",
                "value": "data",
                "value_type": "REG_SZ",
            })
        text = _text(result)
        assert "written" in text.lower()
        mock_winreg.SetValueEx.assert_called_once()

    def test_list_keys(self, stack):
        mock_winreg = self._make_winreg()
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value.__enter__ = MagicMock(return_value=mock_key)
        mock_winreg.OpenKey.return_value.__exit__ = MagicMock(return_value=False)

        # EnumKey returns subkeys, then raises OSError when exhausted
        mock_winreg.EnumKey.side_effect = [
            "SubKey1", "SubKey2", OSError("no more")
        ]
        # EnumValue returns values, then raises OSError
        mock_winreg.EnumValue.side_effect = [
            ("ValueA", "data_a", 1),  # REG_SZ
            OSError("no more"),
        ]

        with patch.dict("sys.modules", {"winreg": mock_winreg}):
            result = _call(stack.mcp, "Registry", {
                "action": "list",
                "key": r"HKLM\SOFTWARE\Test",
            })
        text = _text(result)
        assert "SubKey1" in text
        assert "SubKey2" in text
        assert "ValueA" in text

    def test_read_missing_name(self, stack):
        mock_winreg = self._make_winreg()
        with patch.dict("sys.modules", {"winreg": mock_winreg}):
            result = _call(stack.mcp, "Registry", {
                "action": "read",
                "key": r"HKCU\Software",
            })
        text = _text(result)
        assert "name" in text.lower() and "required" in text.lower()

    def test_unknown_hive(self, stack):
        mock_winreg = self._make_winreg()
        with patch.dict("sys.modules", {"winreg": mock_winreg}):
            result = _call(stack.mcp, "Registry", {
                "action": "read",
                "key": r"BOGUS\Software",
                "name": "x",
            })
        text = _text(result)
        assert "unknown" in text.lower() or "error" in text.lower()

    def test_unknown_action(self, stack):
        mock_winreg = self._make_winreg()
        with patch.dict("sys.modules", {"winreg": mock_winreg}):
            result = _call(stack.mcp, "Registry", {
                "action": "delete",
                "key": r"HKCU\Software",
            })
        text = _text(result)
        assert "unknown action" in text.lower()


# ===================================================================
# 10. Multi tools (MultiSelect, MultiEdit)
# ===================================================================

class TestMultiToolsE2E:
    """MultiSelect and MultiEdit E2E — validates coordinate translation via confinement."""

    def test_multi_select_clicks_positions(self, stack):
        positions = [[100, 200], [300, 400], [500, 600]]
        result = _call(stack.mcp, "MultiSelect", {"positions": positions})
        text = _text(result)
        assert "Clicked 3 positions" in text
        # Verify the input service received absolute coordinates
        calls = stack.input_svc.click.call_args_list
        assert len(calls) == 3
        # First call: rel (100, 200) + offset (3840, 0) = (3940, 200)
        assert calls[0][0] == (3940, 200, "left", 1)
        assert calls[1][0] == (4140, 400, "left", 1)
        assert calls[2][0] == (4340, 600, "left", 1)

    def test_multi_select_right_button(self, stack):
        result = _call(stack.mcp, "MultiSelect", {
            "positions": [[10, 20]],
            "button": "right",
        })
        text = _text(result)
        assert "Clicked 1 positions" in text
        stack.input_svc.click.assert_called_with(3850, 20, "right", 1)

    def test_multi_select_out_of_bounds(self, stack):
        """Coordinates outside the agent screen should trigger a ConfinementError."""
        positions = [[2000, 500]]  # x=2000 >= width 1920
        result = _call(stack.mcp, "MultiSelect", {"positions": positions})
        text = _text(result)
        assert "out of bounds" in text.lower() or "error" in text.lower()

    def test_multi_select_empty_list(self, stack):
        result = _call(stack.mcp, "MultiSelect", {"positions": []})
        text = _text(result)
        assert "Clicked 0 positions" in text

    def test_multi_edit_fills_fields(self, stack):
        fields = [
            {"x": 100, "y": 50, "text": "Alice"},
            {"x": 100, "y": 150, "text": "Bob"},
        ]
        result = _call(stack.mcp, "MultiEdit", {"fields": fields})
        text = _text(result)
        assert "Completed 2/2 fields" in text
        # Verify absolute coords were passed to svc.click
        svc = stack.input_svc
        first_click = svc.click.call_args_list[0]
        assert first_click[0] == (3940, 50, "left", 1)
        # Verify type_text was called with the text
        assert svc.type_text.call_args_list[0][0] == ("Alice",)
        assert svc.type_text.call_args_list[1][0] == ("Bob",)

    def test_multi_edit_confinement_violation(self, stack):
        fields = [
            {"x": 100, "y": 50, "text": "ok"},
            {"x": 5000, "y": 50, "text": "bad"},  # way out of bounds
        ]
        result = _call(stack.mcp, "MultiEdit", {"fields": fields})
        text = _text(result)
        assert "Completed 1/2 fields" in text
        assert "out of bounds" in text.lower() or "stopped" in text.lower()

    def test_multi_edit_bad_field_spec(self, stack):
        fields = [{"x": 100, "text": "missing y"}]
        result = _call(stack.mcp, "MultiEdit", {"fields": fields})
        text = _text(result)
        assert "bad field" in text.lower() or "error" in text.lower()


# ===================================================================
# 11. Scrape
# ===================================================================

class TestScrapeE2E:
    """Scrape tool E2E — mocks urllib."""

    def test_scrape_returns_text(self, stack):
        html_content = b"<html><body><p>Hello World</p></body></html>"
        mock_response = MagicMock()
        mock_response.read.return_value = html_content
        mock_response.headers.get.return_value = "text/html; charset=utf-8"
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = _call(stack.mcp, "Scrape", {"url": "https://example.com"})
        text = _text(result)
        assert "Hello World" in text

    def test_scrape_strips_scripts(self, stack):
        html_content = (
            b"<html><body>"
            b"<script>alert('xss')</script>"
            b"<p>Clean Text</p>"
            b"</body></html>"
        )
        mock_response = MagicMock()
        mock_response.read.return_value = html_content
        mock_response.headers.get.return_value = "text/html"
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = _call(stack.mcp, "Scrape", {"url": "https://example.com"})
        text = _text(result)
        assert "Clean Text" in text
        assert "alert" not in text

    def test_scrape_error_handling(self, stack):
        with patch("urllib.request.urlopen", side_effect=Exception("connection refused")):
            result = _call(stack.mcp, "Scrape", {"url": "https://bad.example.com"})
        text = _text(result)
        assert "error" in text.lower()
        assert "connection refused" in text


# ===================================================================
# Guard integration — verify tools blocked in wrong states
# ===================================================================

class TestGuardIntegration:
    """Verify that tools are properly blocked depending on server state."""

    def test_unconfined_tools_work_in_recovering(self, stack):
        """UNCONFINED tools like PowerShell/FileSystem should work in RECOVERING."""
        stack.state_mgr.transition(ServerState.RECOVERING)
        fake = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr="")
        with patch("subprocess.run", return_value=fake):
            result = _call(stack.mcp, "PowerShell", {"command": "echo ok"})
        text = _text(result)
        assert "ok" in text

    def test_read_tools_blocked_in_recovering(self, stack):
        stack.state_mgr.transition(ServerState.RECOVERING)
        result = _call(stack.mcp, "Screenshot", {"screen": "agent"})
        text = _text(result)
        assert "cannot use" in text.lower() or "recovering" in text.lower()

    def test_write_tools_blocked_in_degraded(self, stack):
        stack.state_mgr.transition(ServerState.DEGRADED, reason="test")
        result = _call(stack.mcp, "App", {"name": "notepad"})
        text = _text(result)
        assert "cannot use" in text.lower() or "degraded" in text.lower()

    def test_all_tools_blocked_in_shutting_down(self, stack):
        stack.state_mgr.transition(ServerState.SHUTTING_DOWN)

        # UNCONFINED
        mock_clipboard = MagicMock()
        mock_con = MagicMock()
        mock_con.CF_UNICODETEXT = 13
        with patch.dict("sys.modules", {
            "win32clipboard": mock_clipboard,
            "win32con": mock_con,
        }):
            result = _call(stack.mcp, "Clipboard", {"action": "get"})
        text = _text(result)
        assert "shutting down" in text.lower()

    def test_recovering_blocks_write(self, stack):
        stack.state_mgr.transition(ServerState.RECOVERING)
        result = _call(stack.mcp, "App", {"name": "x"})
        text = _text(result)
        assert "recovering" in text.lower() or "cannot use" in text.lower()
