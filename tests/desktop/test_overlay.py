"""Tests for windowspc_mcp.desktop.overlay — GhostCursorOverlay and ConflictDetector."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
from unittest.mock import MagicMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FAKE_HWND = 0xDEAD
_FAKE_HWND_2 = 0xBEEF
_FAKE_ATOM = 0x0001
_FAKE_HINSTANCE = 0xCAFE
_FAKE_HDC = 0xDC01
_FAKE_BRUSH = 0xBB01

# Window show commands
SW_HIDE = 0
SW_SHOWNOACTIVATE = 4

# SetWindowPos flags
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

# Colours
COLOR_TRANSPARENT_KEY = 0x00FF00FF
COLOR_WORKING = 0x00FF0000
COLOR_WAITING = 0x00808080

LWA_COLORKEY = 0x00000001


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def win32(monkeypatch):
    """Patch all Win32 functions used by the overlay module.

    Returns a namespace whose attributes are the mock objects.
    """
    import windowspc_mcp.desktop.overlay as mod

    mocks = type("Win32Mocks", (), {})()

    # -- kernel32 --
    mock_kernel32 = MagicMock()
    mock_kernel32.GetModuleHandleW.return_value = _FAKE_HINSTANCE
    mock_kernel32.GetLastError.return_value = 0
    monkeypatch.setattr(mod, "kernel32", mock_kernel32)
    mocks.kernel32 = mock_kernel32

    # -- user32 --
    mock_user32 = MagicMock()
    mock_user32.RegisterClassW.return_value = _FAKE_ATOM
    mock_user32.CreateWindowExW.return_value = _FAKE_HWND
    mock_user32.DestroyWindow.return_value = True
    mock_user32.UnregisterClassW.return_value = True
    mock_user32.ShowWindow.return_value = True
    mock_user32.SetWindowPos.return_value = True
    mock_user32.SetLayeredWindowAttributes.return_value = True
    mock_user32.DefWindowProcW.return_value = 0
    mock_user32.GetDC.return_value = _FAKE_HDC
    mock_user32.ReleaseDC.return_value = 1
    mock_user32.FillRect.return_value = 1
    mock_user32.GetCursorPos.return_value = True
    mock_user32.WindowFromPoint.return_value = _FAKE_HWND
    mock_user32.GetWindowTextW.return_value = 7  # length of "Notepad"
    monkeypatch.setattr(mod, "user32", mock_user32)
    mocks.user32 = mock_user32

    # -- gdi32 --
    mock_gdi32 = MagicMock()
    mock_gdi32.CreateSolidBrush.return_value = _FAKE_BRUSH
    mock_gdi32.DeleteObject.return_value = True
    monkeypatch.setattr(mod, "gdi32", mock_gdi32)
    mocks.gdi32 = mock_gdi32

    return mocks


@pytest.fixture()
def overlay():
    """Return a fresh GhostCursorOverlay instance."""
    from windowspc_mcp.desktop.overlay import GhostCursorOverlay

    return GhostCursorOverlay()


@pytest.fixture()
def detector():
    """Return a fresh ConflictDetector instance."""
    from windowspc_mcp.desktop.overlay import ConflictDetector

    return ConflictDetector()


# ===========================================================================
# GhostCursorOverlay tests
# ===========================================================================


class TestGhostCursorOverlayLifecycle:
    """Create and destroy lifecycle."""

    def test_create_registers_class_and_creates_window(self, win32, overlay):
        overlay.create()

        win32.user32.RegisterClassW.assert_called_once()
        win32.user32.CreateWindowExW.assert_called_once()

    def test_create_sets_layered_window_attributes(self, win32, overlay):
        overlay.create()

        win32.user32.SetLayeredWindowAttributes.assert_called_once_with(
            _FAKE_HWND, COLOR_TRANSPARENT_KEY, 0, LWA_COLORKEY,
        )

    def test_create_starts_hidden(self, win32, overlay):
        overlay.create()

        # The last ShowWindow call during create should be SW_HIDE
        win32.user32.ShowWindow.assert_called_with(_FAKE_HWND, SW_HIDE)

    def test_destroy_destroys_window(self, win32, overlay):
        overlay.create()
        overlay.destroy()

        win32.user32.DestroyWindow.assert_called_once_with(_FAKE_HWND)

    def test_destroy_unregisters_class(self, win32, overlay):
        overlay.create()
        overlay.destroy()

        win32.user32.UnregisterClassW.assert_called_once()

    def test_destroy_is_idempotent(self, win32, overlay):
        overlay.create()
        overlay.destroy()
        overlay.destroy()  # second call should not raise

        # DestroyWindow should only have been called once
        win32.user32.DestroyWindow.assert_called_once()

    def test_destroy_without_create_is_safe(self, win32, overlay):
        """Calling destroy() before create() should not raise."""
        overlay.destroy()  # no-op

    def test_hwnd_is_none_before_create(self, win32, overlay):
        assert overlay._hwnd is None

    def test_hwnd_is_set_after_create(self, win32, overlay):
        overlay.create()
        assert overlay._hwnd == _FAKE_HWND


class TestGhostCursorOverlayPosition:
    """move_to updates position and calls SetWindowPos."""

    def test_move_to_updates_position(self, win32, overlay):
        overlay.create()
        overlay.move_to(100, 200)

        assert overlay.position == (100, 200)

    def test_move_to_calls_set_window_pos(self, win32, overlay):
        from windowspc_mcp.desktop.overlay import HWND_TOPMOST

        overlay.create()
        overlay.move_to(100, 200)

        win32.user32.SetWindowPos.assert_called_once_with(
            _FAKE_HWND,
            HWND_TOPMOST,
            100, 200,
            overlay.CURSOR_SIZE, overlay.CURSOR_SIZE,
            SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )

    def test_move_to_without_create_updates_position_only(self, win32, overlay):
        """move_to before create should store coordinates but not call Win32."""
        overlay.move_to(50, 75)

        assert overlay.position == (50, 75)
        win32.user32.SetWindowPos.assert_not_called()

    def test_initial_position_is_origin(self, win32, overlay):
        assert overlay.position == (0, 0)


class TestGhostCursorOverlayState:
    """set_state behaviour for HIDDEN, WORKING, WAITING."""

    def test_initial_state_is_hidden(self, win32, overlay):
        from windowspc_mcp.desktop.overlay import CursorState

        assert overlay.state is CursorState.HIDDEN

    def test_set_state_hidden_hides_window(self, win32, overlay):
        from windowspc_mcp.desktop.overlay import CursorState

        overlay.create()
        # First switch to WORKING, then HIDDEN
        win32.user32.ShowWindow.reset_mock()
        overlay.set_state(CursorState.HIDDEN)

        win32.user32.ShowWindow.assert_called_with(_FAKE_HWND, SW_HIDE)

    def test_set_state_working_shows_window(self, win32, overlay):
        from windowspc_mcp.desktop.overlay import CursorState

        overlay.create()
        win32.user32.ShowWindow.reset_mock()
        overlay.set_state(CursorState.WORKING)

        win32.user32.ShowWindow.assert_called_with(_FAKE_HWND, SW_SHOWNOACTIVATE)

    def test_set_state_waiting_shows_window(self, win32, overlay):
        from windowspc_mcp.desktop.overlay import CursorState

        overlay.create()
        win32.user32.ShowWindow.reset_mock()
        overlay.set_state(CursorState.WAITING)

        win32.user32.ShowWindow.assert_called_with(_FAKE_HWND, SW_SHOWNOACTIVATE)

    def test_set_state_working_fills_blue(self, win32, overlay):
        from windowspc_mcp.desktop.overlay import CursorState

        overlay.create()
        win32.gdi32.CreateSolidBrush.reset_mock()
        overlay.set_state(CursorState.WORKING)

        win32.gdi32.CreateSolidBrush.assert_called_with(COLOR_WORKING)

    def test_set_state_waiting_fills_gray(self, win32, overlay):
        from windowspc_mcp.desktop.overlay import CursorState

        overlay.create()
        win32.gdi32.CreateSolidBrush.reset_mock()
        overlay.set_state(CursorState.WAITING)

        win32.gdi32.CreateSolidBrush.assert_called_with(COLOR_WAITING)

    def test_state_property_reflects_changes(self, win32, overlay):
        from windowspc_mcp.desktop.overlay import CursorState

        overlay.create()

        overlay.set_state(CursorState.WORKING)
        assert overlay.state is CursorState.WORKING

        overlay.set_state(CursorState.WAITING)
        assert overlay.state is CursorState.WAITING

        overlay.set_state(CursorState.HIDDEN)
        assert overlay.state is CursorState.HIDDEN

    def test_set_state_without_create_updates_state_only(self, win32, overlay):
        """set_state before create should update the property but not call Win32."""
        from windowspc_mcp.desktop.overlay import CursorState

        overlay.set_state(CursorState.WORKING)
        assert overlay.state is CursorState.WORKING
        win32.user32.ShowWindow.assert_not_called()


class TestGhostCursorOverlayWindowStyle:
    """Verify the extended window style flags passed to CreateWindowExW."""

    def test_create_uses_correct_ex_style(self, win32, overlay):
        from windowspc_mcp.desktop.overlay import (
            WS_EX_LAYERED,
            WS_EX_TOOLWINDOW,
            WS_EX_TOPMOST,
            WS_EX_TRANSPARENT,
        )

        overlay.create()

        call_args = win32.user32.CreateWindowExW.call_args[0]
        ex_style = call_args[0]
        expected = WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST | WS_EX_TOOLWINDOW
        assert ex_style == expected

    def test_create_uses_popup_style(self, win32, overlay):
        from windowspc_mcp.desktop.overlay import WS_POPUP

        overlay.create()

        call_args = win32.user32.CreateWindowExW.call_args[0]
        style = call_args[3]
        assert style == WS_POPUP

    def test_create_uses_cursor_size(self, win32, overlay):
        overlay.create()

        call_args = win32.user32.CreateWindowExW.call_args[0]
        width = call_args[6]
        height = call_args[7]
        assert width == overlay.CURSOR_SIZE
        assert height == overlay.CURSOR_SIZE


# ===========================================================================
# ConflictDetector tests
# ===========================================================================


class TestConflictDetectorNoConflict:
    """No conflict when windows are different HWNDs."""

    def test_different_hwnds_returns_none(self, win32, detector):
        """When human and agent target different windows, no conflict."""
        call_count = [0]

        def fake_window_from_point(point):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: human's cursor position
                return _FAKE_HWND
            else:
                # Second call: agent's target position
                return _FAKE_HWND_2

        win32.user32.WindowFromPoint.side_effect = fake_window_from_point

        result = detector.check_conflict(500, 300)
        assert result is None

    def test_agent_target_has_no_window(self, win32, detector):
        """When no window at agent position, no conflict."""
        call_count = [0]

        def fake_window_from_point(point):
            call_count[0] += 1
            if call_count[0] == 1:
                return _FAKE_HWND
            return 0  # No window at agent position

        win32.user32.WindowFromPoint.side_effect = fake_window_from_point

        result = detector.check_conflict(500, 300)
        assert result is None


class TestConflictDetectorConflict:
    """Conflict detected when same HWND, returns window title."""

    def test_same_hwnd_returns_title(self, win32, detector):
        """When human and agent target the same window, return its title."""
        # Both calls return the same HWND
        win32.user32.WindowFromPoint.return_value = _FAKE_HWND

        # Mock GetWindowTextW to write a title into the buffer
        def fake_get_window_text(hwnd, buf, max_count):
            title = "Notepad"
            for i, ch in enumerate(title):
                buf[i] = ch
            buf[len(title)] = "\0"
            return len(title)

        win32.user32.GetWindowTextW.side_effect = fake_get_window_text

        result = detector.check_conflict(100, 200)
        assert result == "Notepad"

    def test_same_hwnd_untitled_window(self, win32, detector):
        """When the conflicting window has no title, return '<untitled>'."""
        win32.user32.WindowFromPoint.return_value = _FAKE_HWND

        # GetWindowTextW writes nothing
        def fake_get_window_text(hwnd, buf, max_count):
            buf[0] = "\0"
            return 0

        win32.user32.GetWindowTextW.side_effect = fake_get_window_text

        result = detector.check_conflict(100, 200)
        assert result == "<untitled>"


class TestConflictDetectorGetHumanWindow:
    """get_human_window returns HWND from WindowFromPoint."""

    def test_returns_hwnd(self, win32, detector):
        win32.user32.WindowFromPoint.return_value = _FAKE_HWND

        result = detector.get_human_window()
        assert result == _FAKE_HWND

    def test_get_cursor_pos_failure_returns_none(self, win32, detector):
        """When GetCursorPos fails, return None."""
        win32.user32.GetCursorPos.return_value = False

        result = detector.get_human_window()
        assert result is None

    def test_no_window_at_cursor_returns_none(self, win32, detector):
        """When WindowFromPoint returns 0 (no window), return None."""
        win32.user32.WindowFromPoint.return_value = 0

        result = detector.get_human_window()
        assert result is None


class TestConflictDetectorEdgeCases:
    """Edge cases and graceful degradation."""

    def test_get_cursor_pos_failure_in_check_conflict(self, win32, detector):
        """If human position can't be determined, assume no conflict."""
        win32.user32.GetCursorPos.return_value = False

        result = detector.check_conflict(100, 200)
        assert result is None
