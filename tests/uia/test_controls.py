"""Tests for windowspc_mcp.uia.controls — window helpers and input helpers."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
from unittest.mock import MagicMock, patch, call

import pytest


# ===================================================================
# Window helpers
# ===================================================================


class TestGetForegroundWindow:
    def test_returns_hwnd(self):
        with patch("windowspc_mcp.uia.controls.user32") as mock_u32:
            mock_u32.GetForegroundWindow.return_value = 12345
            from windowspc_mcp.uia.controls import get_foreground_window
            assert get_foreground_window() == 12345
            mock_u32.GetForegroundWindow.assert_called_once()


class TestSetForegroundWindow:
    """set_foreground_window — visibility check, AttachThreadInput trick."""

    def test_restores_if_not_visible(self):
        with patch("windowspc_mcp.uia.controls.user32") as mock_u32, \
             patch("ctypes.windll.kernel32.GetCurrentThreadId", return_value=100):
            mock_u32.IsWindowVisible.return_value = False
            mock_u32.GetForegroundWindow.return_value = 9999
            mock_u32.GetWindowThreadProcessId.return_value = 200
            mock_u32.SetForegroundWindow.return_value = True

            from windowspc_mcp.uia.controls import set_foreground_window
            result = set_foreground_window(42)

            # Should call ShowWindow with SW_SHOW (5) since not visible
            mock_u32.ShowWindow.assert_called_once_with(42, 5)
            assert result is True

    def test_sw_restore_if_visible(self):
        with patch("windowspc_mcp.uia.controls.user32") as mock_u32, \
             patch("ctypes.windll.kernel32.GetCurrentThreadId", return_value=100):
            mock_u32.IsWindowVisible.return_value = True
            mock_u32.GetForegroundWindow.return_value = 9999
            mock_u32.GetWindowThreadProcessId.return_value = 200
            mock_u32.SetForegroundWindow.return_value = True

            from windowspc_mcp.uia.controls import set_foreground_window
            result = set_foreground_window(42)

            # Should call ShowWindow with SW_RESTORE (9) since visible
            from windowspc_mcp.uia.core import SW_RESTORE
            mock_u32.ShowWindow.assert_called_once_with(42, SW_RESTORE)
            assert result is True

    def test_attach_thread_input_when_different_thread(self):
        with patch("windowspc_mcp.uia.controls.user32") as mock_u32, \
             patch("ctypes.windll.kernel32.GetCurrentThreadId", return_value=100):
            mock_u32.IsWindowVisible.return_value = True
            mock_u32.GetForegroundWindow.return_value = 9999
            mock_u32.GetWindowThreadProcessId.return_value = 200  # different from 100
            mock_u32.SetForegroundWindow.return_value = True

            from windowspc_mcp.uia.controls import set_foreground_window
            set_foreground_window(42)

            # AttachThreadInput called with True then False
            calls = mock_u32.AttachThreadInput.call_args_list
            assert len(calls) == 2
            assert calls[0] == call(100, 200, True)
            assert calls[1] == call(100, 200, False)

    def test_no_attach_when_same_thread(self):
        with patch("windowspc_mcp.uia.controls.user32") as mock_u32, \
             patch("ctypes.windll.kernel32.GetCurrentThreadId", return_value=100):
            mock_u32.IsWindowVisible.return_value = True
            mock_u32.GetForegroundWindow.return_value = 9999
            mock_u32.GetWindowThreadProcessId.return_value = 100  # same as cur_tid
            mock_u32.SetForegroundWindow.return_value = True

            from windowspc_mcp.uia.controls import set_foreground_window
            set_foreground_window(42)

            mock_u32.AttachThreadInput.assert_not_called()

    def test_no_attach_when_fg_tid_zero(self):
        with patch("windowspc_mcp.uia.controls.user32") as mock_u32, \
             patch("ctypes.windll.kernel32.GetCurrentThreadId", return_value=100):
            mock_u32.IsWindowVisible.return_value = True
            mock_u32.GetForegroundWindow.return_value = 0
            mock_u32.GetWindowThreadProcessId.return_value = 0  # falsy
            mock_u32.SetForegroundWindow.return_value = False

            from windowspc_mcp.uia.controls import set_foreground_window
            result = set_foreground_window(42)

            mock_u32.AttachThreadInput.assert_not_called()
            assert result is False

    def test_returns_false_on_failure(self):
        with patch("windowspc_mcp.uia.controls.user32") as mock_u32, \
             patch("ctypes.windll.kernel32.GetCurrentThreadId", return_value=100):
            mock_u32.IsWindowVisible.return_value = True
            mock_u32.GetForegroundWindow.return_value = 0
            mock_u32.GetWindowThreadProcessId.return_value = 0
            mock_u32.SetForegroundWindow.return_value = 0

            from windowspc_mcp.uia.controls import set_foreground_window
            result = set_foreground_window(42)
            assert result is False


class TestGetWindowRect:
    def test_returns_tuple_on_success(self):
        mock_rect = MagicMock()
        mock_rect.left = 10
        mock_rect.top = 20
        mock_rect.right = 310
        mock_rect.bottom = 220

        with patch("windowspc_mcp.uia.controls.user32") as mock_u32, \
             patch("windowspc_mcp.uia.controls.ctypes.wintypes.RECT", return_value=mock_rect), \
             patch("windowspc_mcp.uia.controls.ctypes.byref", return_value="byref_rect"):
            mock_u32.GetWindowRect.return_value = True

            from windowspc_mcp.uia.controls import get_window_rect
            result = get_window_rect(42)
            assert result == (10, 20, 310, 220)
            mock_u32.GetWindowRect.assert_called_once_with(42, "byref_rect")

    def test_returns_none_on_failure(self):
        with patch("windowspc_mcp.uia.controls.user32") as mock_u32, \
             patch("windowspc_mcp.uia.controls.ctypes.wintypes.RECT"), \
             patch("windowspc_mcp.uia.controls.ctypes.byref"):
            mock_u32.GetWindowRect.return_value = False

            from windowspc_mcp.uia.controls import get_window_rect
            result = get_window_rect(0)
            assert result is None


class TestMoveWindow:
    def test_calls_user32_and_returns_bool(self):
        with patch("windowspc_mcp.uia.controls.user32") as mock_u32:
            mock_u32.MoveWindow.return_value = True
            from windowspc_mcp.uia.controls import move_window
            assert move_window(42, 10, 20, 300, 200) is True
            mock_u32.MoveWindow.assert_called_once_with(42, 10, 20, 300, 200, True)

    def test_returns_false_on_failure(self):
        with patch("windowspc_mcp.uia.controls.user32") as mock_u32:
            mock_u32.MoveWindow.return_value = 0
            from windowspc_mcp.uia.controls import move_window
            assert move_window(0, 0, 0, 0, 0) is False


class TestGetWindowTitle:
    def test_returns_title(self):
        with patch("windowspc_mcp.uia.controls.user32") as mock_u32:
            mock_u32.GetWindowTextLengthW.return_value = 5

            def fake_get_text(hwnd, buf, size):
                buf.value = "Hello"
                return 5

            mock_u32.GetWindowTextW.side_effect = fake_get_text

            from windowspc_mcp.uia.controls import get_window_title

            # We need to also patch create_unicode_buffer to return a proper mock
            with patch("windowspc_mcp.uia.controls.ctypes.create_unicode_buffer") as mock_buf:
                mock_buffer = MagicMock()
                mock_buffer.value = "Hello"
                mock_buf.return_value = mock_buffer

                result = get_window_title(42)
                assert result == "Hello"

    def test_returns_empty_string_when_length_zero(self):
        with patch("windowspc_mcp.uia.controls.user32") as mock_u32:
            mock_u32.GetWindowTextLengthW.return_value = 0
            from windowspc_mcp.uia.controls import get_window_title
            result = get_window_title(42)
            assert result == ""
            mock_u32.GetWindowTextW.assert_not_called()


class TestGetWindowClass:
    def test_returns_class_name(self):
        with patch("windowspc_mcp.uia.controls.user32") as mock_u32, \
             patch("windowspc_mcp.uia.controls.ctypes.create_unicode_buffer") as mock_buf:
            mock_buffer = MagicMock()
            mock_buffer.value = "CabinetWClass"
            mock_buf.return_value = mock_buffer

            from windowspc_mcp.uia.controls import get_window_class
            result = get_window_class(42)
            assert result == "CabinetWClass"
            mock_u32.GetClassNameW.assert_called_once_with(42, mock_buffer, 256)


class TestGetWindowPid:
    def test_returns_pid(self):
        with patch("windowspc_mcp.uia.controls.user32") as mock_u32, \
             patch("windowspc_mcp.uia.controls.ctypes.wintypes.DWORD") as mock_dword, \
             patch("windowspc_mcp.uia.controls.ctypes.byref") as mock_byref:
            mock_pid = MagicMock()
            mock_pid.value = 1234
            mock_dword.return_value = mock_pid
            mock_byref.return_value = "byref_pid"

            from windowspc_mcp.uia.controls import get_window_pid
            result = get_window_pid(42)
            assert result == 1234
            mock_u32.GetWindowThreadProcessId.assert_called_once_with(42, "byref_pid")


class TestGetRootWindow:
    def test_returns_root_ancestor(self):
        with patch("windowspc_mcp.uia.controls.user32") as mock_u32:
            mock_u32.GetAncestor.return_value = 1000
            from windowspc_mcp.uia.controls import get_root_window
            from windowspc_mcp.uia.core import GA_ROOT
            result = get_root_window(42)
            assert result == 1000
            mock_u32.GetAncestor.assert_called_once_with(42, GA_ROOT)


class TestIsWindowVisible:
    def test_visible(self):
        with patch("windowspc_mcp.uia.controls.user32") as mock_u32:
            mock_u32.IsWindowVisible.return_value = 1
            from windowspc_mcp.uia.controls import is_window_visible
            assert is_window_visible(42) is True

    def test_not_visible(self):
        with patch("windowspc_mcp.uia.controls.user32") as mock_u32:
            mock_u32.IsWindowVisible.return_value = 0
            from windowspc_mcp.uia.controls import is_window_visible
            assert is_window_visible(42) is False


class TestEnumerateWindows:
    def test_collects_hwnds_via_callback(self):
        with patch("windowspc_mcp.uia.controls.user32") as mock_u32, \
             patch("windowspc_mcp.uia.controls.WNDENUMPROC") as mock_wndproc:
            # Capture the callback passed to WNDENUMPROC
            captured_cb = None

            def capture_cb(cb):
                nonlocal captured_cb
                captured_cb = cb
                return "wrapped_cb"

            mock_wndproc.side_effect = capture_cb

            def fake_enum(cb, lparam):
                # Simulate Windows calling our callback with some HWNDs
                captured_cb(111, 0)
                captured_cb(222, 0)
                captured_cb(333, 0)
                return True

            mock_u32.EnumWindows.side_effect = fake_enum

            from windowspc_mcp.uia.controls import enumerate_windows
            result = enumerate_windows()
            assert result == [111, 222, 333]

    def test_returns_empty_list_when_no_windows(self):
        with patch("windowspc_mcp.uia.controls.user32") as mock_u32, \
             patch("windowspc_mcp.uia.controls.WNDENUMPROC"):
            mock_u32.EnumWindows.return_value = True

            from windowspc_mcp.uia.controls import enumerate_windows
            result = enumerate_windows()
            assert result == []


# ===================================================================
# Coordinate normalization
# ===================================================================


class TestNormalizeCoords:
    """_normalize_coords — maps screen coords to 0..65535 range."""

    def test_basic_normalization(self):
        with patch("windowspc_mcp.uia.controls.user32") as mock_u32:
            # Virtual screen: origin (0, 0), size 1920x1080
            def fake_metrics(idx):
                return {76: 0, 77: 0, 78: 1920, 79: 1080}[idx]

            mock_u32.GetSystemMetrics.side_effect = fake_metrics

            from windowspc_mcp.uia.controls import _normalize_coords
            nx, ny = _normalize_coords(960, 540)
            # 960 / 1920 * 65535 = 32767
            # 540 / 1080 * 65535 = 32767
            assert nx == 960 * 65535 // 1920
            assert ny == 540 * 65535 // 1080

    def test_with_offset_virtual_screen(self):
        with patch("windowspc_mcp.uia.controls.user32") as mock_u32:
            # Virtual screen starts at (100, 50), size 3840x2160
            def fake_metrics(idx):
                return {76: 100, 77: 50, 78: 3840, 79: 2160}[idx]

            mock_u32.GetSystemMetrics.side_effect = fake_metrics

            from windowspc_mcp.uia.controls import _normalize_coords
            nx, ny = _normalize_coords(100, 50)  # top-left of virtual screen
            assert nx == 0
            assert ny == 0

    def test_zero_width_protection(self):
        """Division by zero is avoided when vw or vh is 0."""
        with patch("windowspc_mcp.uia.controls.user32") as mock_u32:
            def fake_metrics(idx):
                return {76: 0, 77: 0, 78: 0, 79: 0}[idx]

            mock_u32.GetSystemMetrics.side_effect = fake_metrics

            from windowspc_mcp.uia.controls import _normalize_coords
            # Should not raise ZeroDivisionError
            nx, ny = _normalize_coords(100, 100)
            # vw and vh clamped to 1
            assert nx == 100 * 65535 // 1
            assert ny == 100 * 65535 // 1

    def test_negative_width_protection(self):
        """Negative dimensions are clamped to 1."""
        with patch("windowspc_mcp.uia.controls.user32") as mock_u32:
            def fake_metrics(idx):
                return {76: 0, 77: 0, 78: -10, 79: -20}[idx]

            mock_u32.GetSystemMetrics.side_effect = fake_metrics

            from windowspc_mcp.uia.controls import _normalize_coords
            nx, ny = _normalize_coords(50, 50)
            assert nx == 50 * 65535 // 1
            assert ny == 50 * 65535 // 1


# ===================================================================
# Mouse / keyboard input helpers
# ===================================================================


class TestMakeMouseInput:
    def test_creates_input_with_flags(self):
        from windowspc_mcp.uia.controls import _make_mouse_input
        from windowspc_mcp.uia.core import INPUT_MOUSE, MOUSEEVENTF_LEFTDOWN

        inp = _make_mouse_input(MOUSEEVENTF_LEFTDOWN, dx=100, dy=200, data=0)
        assert inp.type == INPUT_MOUSE
        assert inp._input.mi.dx == 100
        assert inp._input.mi.dy == 200
        assert inp._input.mi.dwFlags == MOUSEEVENTF_LEFTDOWN

    def test_default_dx_dy_data(self):
        from windowspc_mcp.uia.controls import _make_mouse_input

        inp = _make_mouse_input(0x0001)
        assert inp._input.mi.dx == 0
        assert inp._input.mi.dy == 0
        assert inp._input.mi.mouseData == 0


class TestMakeKeyInput:
    def test_creates_keyboard_input(self):
        from windowspc_mcp.uia.controls import _make_key_input
        from windowspc_mcp.uia.core import INPUT_KEYBOARD, KEYEVENTF_UNICODE

        inp = _make_key_input(65, KEYEVENTF_UNICODE)
        assert inp.type == INPUT_KEYBOARD
        assert inp._input.ki.wVk == 0
        assert inp._input.ki.wScan == 65
        assert inp._input.ki.dwFlags == KEYEVENTF_UNICODE


class TestClickAt:
    """click_at — absolute click using SendInput."""

    def test_left_single_click(self):
        with patch("windowspc_mcp.uia.controls._normalize_coords", return_value=(32767, 32767)), \
             patch("windowspc_mcp.uia.controls.send_input") as mock_si:

            from windowspc_mcp.uia.controls import click_at
            click_at(960, 540, button="left", clicks=1)

            mock_si.assert_called_once()
            args = mock_si.call_args[0]
            # 1 move + 1 down + 1 up = 3 inputs
            assert len(args) == 3

    def test_right_click(self):
        with patch("windowspc_mcp.uia.controls._normalize_coords", return_value=(100, 200)), \
             patch("windowspc_mcp.uia.controls.send_input") as mock_si:

            from windowspc_mcp.uia.controls import click_at
            click_at(10, 20, button="right")

            mock_si.assert_called_once()
            args = mock_si.call_args[0]
            assert len(args) == 3

    def test_middle_click(self):
        with patch("windowspc_mcp.uia.controls._normalize_coords", return_value=(100, 200)), \
             patch("windowspc_mcp.uia.controls.send_input") as mock_si:

            from windowspc_mcp.uia.controls import click_at
            click_at(10, 20, button="middle")

            mock_si.assert_called_once()

    def test_double_click(self):
        with patch("windowspc_mcp.uia.controls._normalize_coords", return_value=(100, 200)), \
             patch("windowspc_mcp.uia.controls.send_input") as mock_si:

            from windowspc_mcp.uia.controls import click_at
            click_at(10, 20, clicks=2)

            args = mock_si.call_args[0]
            # 1 move + 2 * (down + up) = 5 inputs
            assert len(args) == 5

    def test_unknown_button_defaults_to_left(self):
        with patch("windowspc_mcp.uia.controls._normalize_coords", return_value=(100, 200)), \
             patch("windowspc_mcp.uia.controls.send_input") as mock_si:

            from windowspc_mcp.uia.controls import click_at
            click_at(10, 20, button="nonexistent")

            # Should fall back to left button
            mock_si.assert_called_once()
            args = mock_si.call_args[0]
            assert len(args) == 3


class TestTypeText:
    """type_text — Unicode SendInput events."""

    def test_types_each_character(self):
        with patch("windowspc_mcp.uia.controls.send_input") as mock_si:
            from windowspc_mcp.uia.controls import type_text
            type_text("Hi")

            mock_si.assert_called_once()
            args = mock_si.call_args[0]
            # 2 chars * 2 events (down + up) = 4 inputs
            assert len(args) == 4

    def test_empty_string_no_send(self):
        with patch("windowspc_mcp.uia.controls.send_input") as mock_si:
            from windowspc_mcp.uia.controls import type_text
            type_text("")

            mock_si.assert_not_called()

    def test_unicode_characters(self):
        with patch("windowspc_mcp.uia.controls.send_input") as mock_si:
            from windowspc_mcp.uia.controls import type_text
            type_text("\u00e9")  # é

            mock_si.assert_called_once()
            args = mock_si.call_args[0]
            assert len(args) == 2  # 1 char * 2 events

    def test_scan_codes_match_ord(self):
        """Verify scan codes are set to ord(char)."""
        with patch("windowspc_mcp.uia.controls.send_input") as mock_si:
            from windowspc_mcp.uia.controls import type_text
            type_text("A")

            args = mock_si.call_args[0]
            down_input = args[0]
            up_input = args[1]
            assert down_input._input.ki.wScan == ord("A")
            assert up_input._input.ki.wScan == ord("A")


class TestScrollAt:
    """scroll_at — wheel scrolling at coordinates."""

    def test_vertical_scroll(self):
        with patch("windowspc_mcp.uia.controls.user32") as mock_u32, \
             patch("windowspc_mcp.uia.controls.send_input") as mock_si:
            from windowspc_mcp.uia.controls import scroll_at
            scroll_at(100, 200, amount=3, horizontal=False)

            mock_u32.SetCursorPos.assert_called_once_with(100, 200)
            mock_si.assert_called_once()
            inp = mock_si.call_args[0][0]
            # MOUSEEVENTF_WHEEL = 0x0800
            assert inp._input.mi.dwFlags == 0x0800
            assert inp._input.mi.mouseData == 3 * 120

    def test_horizontal_scroll(self):
        with patch("windowspc_mcp.uia.controls.user32") as mock_u32, \
             patch("windowspc_mcp.uia.controls.send_input") as mock_si:
            from windowspc_mcp.uia.controls import scroll_at
            scroll_at(100, 200, amount=2, horizontal=True)

            mock_u32.SetCursorPos.assert_called_once_with(100, 200)
            mock_si.assert_called_once()
            inp = mock_si.call_args[0][0]
            # MOUSEEVENTF_HWHEEL = 0x01000
            assert inp._input.mi.dwFlags == 0x01000
            assert inp._input.mi.mouseData == 2 * 120

    def test_negative_amount(self):
        """Negative amount scrolls down/left."""
        with patch("windowspc_mcp.uia.controls.user32"), \
             patch("windowspc_mcp.uia.controls.send_input") as mock_si:
            from windowspc_mcp.uia.controls import scroll_at
            scroll_at(0, 0, amount=-5)

            inp = mock_si.call_args[0][0]
            # mouseData is c_ulong, but the value should encode negative
            # as unsigned; the key point is it's amount * WHEEL_DELTA
            expected = (-5 * 120) & 0xFFFFFFFF  # unsigned representation
            assert inp._input.mi.mouseData == expected


class TestMoveCursor:
    def test_returns_true_on_success(self):
        with patch("windowspc_mcp.uia.controls.user32") as mock_u32:
            mock_u32.SetCursorPos.return_value = 1
            from windowspc_mcp.uia.controls import move_cursor
            assert move_cursor(100, 200) is True
            mock_u32.SetCursorPos.assert_called_once_with(100, 200)

    def test_returns_false_on_failure(self):
        with patch("windowspc_mcp.uia.controls.user32") as mock_u32:
            mock_u32.SetCursorPos.return_value = 0
            from windowspc_mcp.uia.controls import move_cursor
            assert move_cursor(0, 0) is False
