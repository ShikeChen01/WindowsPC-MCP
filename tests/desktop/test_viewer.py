"""Tests for windowspc_mcp.desktop.viewer -- ViewerWindow class."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import threading
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Constants mirroring the module under test
# ---------------------------------------------------------------------------

_FAKE_HWND = 0xDEAD
_FAKE_ATOM = 0x0001
_FAKE_HINSTANCE = 0xCAFE
_FAKE_THREAD_ID = 8888
_FAKE_HDC = 0xBBBB

WM_PAINT = 0x000F
WM_TIMER = 0x0113
WM_CLOSE = 0x0010
WM_DESTROY = 0x0002
WM_QUIT = 0x0012

WS_OVERLAPPEDWINDOW = 0x00CF0000
SW_SHOWNOACTIVATE = 4
HALFTONE = 4
TIMER_ID = 1

_WIDTH = 1920
_HEIGHT = 1080
_FPS = 30


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def _win32(monkeypatch):
    """Patch all Win32 functions used by the viewer module.

    Returns a namespace whose attributes are the mock objects so tests can
    inspect calls and override return values.
    """
    import windowspc_mcp.desktop.viewer as mod

    mocks = type("Win32Mocks", (), {})()

    # -- kernel32 --
    mock_kernel32 = MagicMock()
    mock_kernel32.GetCurrentThreadId.return_value = _FAKE_THREAD_ID
    mock_kernel32.GetModuleHandleW.return_value = _FAKE_HINSTANCE
    monkeypatch.setattr(mod, "kernel32", mock_kernel32)
    mocks.kernel32 = mock_kernel32

    # -- ctypes.get_last_error --
    monkeypatch.setattr(ctypes, "get_last_error", lambda: mocks._last_error)
    mocks._last_error = 0

    # -- user32 --
    mock_user32 = MagicMock()
    mock_user32.RegisterClassW.return_value = _FAKE_ATOM
    mock_user32.CreateWindowExW.return_value = _FAKE_HWND
    mock_user32.ShowWindow.return_value = True
    mock_user32.SetTimer.return_value = TIMER_ID
    mock_user32.KillTimer.return_value = True
    mock_user32.DestroyWindow.return_value = True
    mock_user32.UnregisterClassW.return_value = True
    mock_user32.PostThreadMessageW.return_value = True
    mock_user32.DefWindowProcW.return_value = 0
    mock_user32.TranslateMessage.return_value = True
    mock_user32.DispatchMessageW.return_value = 0
    mock_user32.InvalidateRect.return_value = True
    mock_user32.BeginPaint.return_value = _FAKE_HDC
    mock_user32.EndPaint.return_value = True
    mock_user32.PostQuitMessage.return_value = None
    mock_user32.GetClientRect.return_value = True

    # GetMessageW: immediately quit by default.
    mock_user32.GetMessageW.return_value = 0

    monkeypatch.setattr(mod, "user32", mock_user32)
    mocks.user32 = mock_user32

    # -- gdi32 --
    mock_gdi32 = MagicMock()
    mock_gdi32.StretchDIBits.return_value = _HEIGHT
    mock_gdi32.SetStretchBltMode.return_value = 0
    monkeypatch.setattr(mod, "gdi32", mock_gdi32)
    mocks.gdi32 = mock_gdi32

    return mocks


@pytest.fixture()
def win32(_win32):
    return _win32


@pytest.fixture()
def frame_buffer():
    """Return a FrameBuffer pre-populated with fake frame data."""
    from windowspc_mcp.desktop.capture import FrameBuffer

    fb = FrameBuffer(
        width=_WIDTH,
        height=_HEIGHT,
        data=b"\x00\x00\xFF\xFF" * (_WIDTH * _HEIGHT),  # BGRA
        timestamp_ns=1000000,
    )
    return fb


@pytest.fixture()
def viewer(frame_buffer):
    """Return a fresh ViewerWindow (Win32 calls still need patching)."""
    from windowspc_mcp.desktop.viewer import ViewerWindow

    return ViewerWindow(frame_buffer, fps=_FPS)


# ---------------------------------------------------------------------------
# Start / stop lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    def test_start_creates_thread(self, win32, viewer):
        """start() should create a daemon thread."""
        viewer.start()
        assert viewer._thread is not None
        assert viewer._thread.daemon is True
        assert viewer._thread.name == "ViewerWindow"
        viewer.stop()

    def test_thread_is_joined_on_stop(self, win32, viewer):
        """stop() should join the viewer thread."""
        viewer.start()
        thread = viewer._thread
        assert thread is not None
        viewer.stop()
        assert not thread.is_alive()
        assert viewer._thread is None

    def test_is_running_reflects_state(self, win32, viewer):
        """is_running should be False before start, True during, False after."""
        assert not viewer.is_running

        _setup_blocking_getmessage(win32)
        viewer.start()
        assert viewer.is_running

        viewer.stop()
        assert not viewer.is_running

    def test_hwnd_property(self, win32, viewer):
        """hwnd should be None before start, non-None during."""
        assert viewer.hwnd is None

        _setup_blocking_getmessage(win32)
        viewer.start()
        assert viewer.hwnd == _FAKE_HWND
        viewer.stop()
        # After stop, hwnd is cleared by cleanup
        assert viewer.hwnd is None


# ---------------------------------------------------------------------------
# Window class registration
# ---------------------------------------------------------------------------


class TestWindowClassRegistration:
    def test_register_class_called_with_correct_name(self, win32, viewer):
        """RegisterClassW should be called with WINDOW_CLASS_NAME."""
        viewer.start()
        viewer.stop()

        win32.user32.RegisterClassW.assert_called_once()
        # The arg is a byref to WNDCLASSW; check call was made.

    def test_register_class_already_exists_tolerated(self, win32, viewer):
        """ERROR_CLASS_ALREADY_EXISTS (1410) should not raise."""
        win32.user32.RegisterClassW.return_value = 0
        win32._last_error = 1410

        viewer.start()
        viewer.stop()

    def test_register_class_failure_raises(self, win32, viewer):
        """Non-1410 failure should raise InvalidStateError."""
        from windowspc_mcp.confinement.errors import InvalidStateError

        win32.user32.RegisterClassW.return_value = 0
        win32._last_error = 87  # ERROR_INVALID_PARAMETER

        with pytest.raises(InvalidStateError, match="RegisterClassW failed"):
            viewer.start()

    def test_unregister_class_on_cleanup(self, win32, viewer):
        """UnregisterClassW should be called on cleanup."""
        viewer.start()
        viewer.stop()

        win32.user32.UnregisterClassW.assert_called_once()


# ---------------------------------------------------------------------------
# Window creation
# ---------------------------------------------------------------------------


class TestWindowCreation:
    def test_created_with_ws_overlappedwindow(self, win32, viewer):
        """Window should be created with WS_OVERLAPPEDWINDOW style."""
        viewer.start()
        viewer.stop()

        win32.user32.CreateWindowExW.assert_called_once()
        args = win32.user32.CreateWindowExW.call_args[0]
        # args[3] is dwStyle
        assert args[3] == WS_OVERLAPPEDWINDOW

    def test_created_with_correct_class_and_title(self, win32, viewer):
        """Window should use the correct class name and title."""
        viewer.start()
        viewer.stop()

        args = win32.user32.CreateWindowExW.call_args[0]
        # args[1] is lpClassName, args[2] is lpWindowName
        assert args[1] == "WindowsPC_MCP_Viewer"
        assert args[2] == "Agent Desktop Viewer"

    def test_created_with_frame_buffer_dimensions(self, win32, viewer):
        """Window initial size should match frame_buffer width/height."""
        viewer.start()
        viewer.stop()

        args = win32.user32.CreateWindowExW.call_args[0]
        # args[6] is nWidth, args[7] is nHeight
        assert args[6] == _WIDTH
        assert args[7] == _HEIGHT

    def test_create_window_failure_raises(self, win32, viewer):
        """If CreateWindowExW fails, start() should propagate error."""
        from windowspc_mcp.confinement.errors import InvalidStateError

        win32.user32.CreateWindowExW.return_value = 0
        win32._last_error = 1400

        with pytest.raises(InvalidStateError, match="CreateWindowExW failed"):
            viewer.start()


# ---------------------------------------------------------------------------
# ShowWindow
# ---------------------------------------------------------------------------


class TestShowWindow:
    def test_show_window_called_with_sw_shownoactivate(self, win32, viewer):
        """ShowWindow should be called with SW_SHOWNOACTIVATE."""
        viewer.start()
        viewer.stop()

        win32.user32.ShowWindow.assert_called_once_with(
            _FAKE_HWND, SW_SHOWNOACTIVATE
        )


# ---------------------------------------------------------------------------
# SetTimer
# ---------------------------------------------------------------------------


class TestSetTimer:
    def test_set_timer_called_with_correct_interval(self, win32, viewer):
        """SetTimer should be called with interval = 1000 / fps."""
        viewer.start()
        viewer.stop()

        expected_interval = 1000 // _FPS  # 33 ms for 30 fps
        win32.user32.SetTimer.assert_called_once_with(
            _FAKE_HWND, TIMER_ID, expected_interval, None
        )

    def test_set_timer_interval_for_60fps(self, win32, frame_buffer):
        """SetTimer interval should be 16ms at 60fps."""
        from windowspc_mcp.desktop.viewer import ViewerWindow

        v = ViewerWindow(frame_buffer, fps=60)
        v.start()
        v.stop()

        expected_interval = 1000 // 60  # 16 ms
        win32.user32.SetTimer.assert_called_once_with(
            _FAKE_HWND, TIMER_ID, expected_interval, None
        )


# ---------------------------------------------------------------------------
# WM_TIMER triggers InvalidateRect
# ---------------------------------------------------------------------------


class TestWMTimer:
    def test_wm_timer_triggers_invalidate_rect(self, win32, viewer):
        """WM_TIMER in the wndproc should call InvalidateRect."""
        from windowspc_mcp.desktop.viewer import WM_TIMER

        viewer.start()
        viewer.stop()

        # Call the wndproc directly with WM_TIMER
        result = viewer._wndproc(_FAKE_HWND, WM_TIMER, 0, 0)
        assert result == 0

        win32.user32.InvalidateRect.assert_called_with(_FAKE_HWND, None, False)


# ---------------------------------------------------------------------------
# WM_PAINT triggers rendering pipeline
# ---------------------------------------------------------------------------


class TestWMPaint:
    def test_wm_paint_calls_begin_end_paint(self, win32, viewer):
        """WM_PAINT should call BeginPaint and EndPaint."""
        viewer.start()
        viewer.stop()

        # Call the wndproc with WM_PAINT
        result = viewer._wndproc(_FAKE_HWND, WM_PAINT, 0, 0)
        assert result == 0

        win32.user32.BeginPaint.assert_called_once()
        win32.user32.EndPaint.assert_called_once()

    def test_wm_paint_calls_stretch_dib_its(self, win32, viewer, frame_buffer):
        """WM_PAINT should call StretchDIBits with correct frame dimensions."""
        viewer.start()
        viewer.stop()

        # Call the wndproc with WM_PAINT
        viewer._wndproc(_FAKE_HWND, WM_PAINT, 0, 0)

        win32.gdi32.StretchDIBits.assert_called_once()
        args = win32.gdi32.StretchDIBits.call_args[0]

        # args: hdc, xDest, yDest, wDest, hDest, xSrc, ySrc, wSrc, hSrc, bits, bmi, usage, rop
        assert args[0] == _FAKE_HDC   # hdc from BeginPaint
        assert args[5] == 0           # xSrc
        assert args[6] == 0           # ySrc
        assert args[7] == _WIDTH      # wSrc
        assert args[8] == _HEIGHT     # hSrc

    def test_wm_paint_sets_halftone_stretch_mode(self, win32, viewer):
        """WM_PAINT should call SetStretchBltMode(hdc, HALFTONE)."""
        viewer.start()
        viewer.stop()

        viewer._wndproc(_FAKE_HWND, WM_PAINT, 0, 0)

        win32.gdi32.SetStretchBltMode.assert_called_once_with(
            _FAKE_HDC, HALFTONE
        )

    def test_wm_paint_no_data_skips_stretch(self, win32, frame_buffer, viewer):
        """If frame_buffer.data is empty, StretchDIBits should NOT be called."""
        frame_buffer.data = b""

        viewer.start()
        viewer.stop()

        viewer._wndproc(_FAKE_HWND, WM_PAINT, 0, 0)

        win32.gdi32.StretchDIBits.assert_not_called()

    def test_wm_paint_still_calls_end_paint_on_empty(self, win32, frame_buffer, viewer):
        """Even with no data, EndPaint must be called."""
        frame_buffer.data = b""

        viewer.start()
        viewer.stop()

        viewer._wndproc(_FAKE_HWND, WM_PAINT, 0, 0)

        win32.user32.BeginPaint.assert_called_once()
        win32.user32.EndPaint.assert_called_once()


# ---------------------------------------------------------------------------
# StretchDIBits receives correct bitmap info
# ---------------------------------------------------------------------------


class TestStretchDIBitsData:
    def test_receives_frame_data(self, win32, viewer, frame_buffer):
        """StretchDIBits should receive the frame_buffer's data."""
        viewer.start()
        viewer.stop()

        viewer._wndproc(_FAKE_HWND, WM_PAINT, 0, 0)

        args = win32.gdi32.StretchDIBits.call_args[0]
        # args[9] is the pixel data
        assert args[9] == frame_buffer.data


# ---------------------------------------------------------------------------
# WM_CLOSE triggers DestroyWindow
# ---------------------------------------------------------------------------


class TestWMClose:
    def test_wm_close_destroys_window(self, win32, viewer):
        """WM_CLOSE should call DestroyWindow."""
        viewer.start()
        viewer.stop()

        viewer._wndproc(_FAKE_HWND, WM_CLOSE, 0, 0)

        win32.user32.DestroyWindow.assert_called_with(_FAKE_HWND)

    def test_wm_destroy_posts_quit(self, win32, viewer):
        """WM_DESTROY should call PostQuitMessage(0)."""
        viewer.start()
        viewer.stop()

        viewer._wndproc(_FAKE_HWND, WM_DESTROY, 0, 0)

        win32.user32.PostQuitMessage.assert_called_with(0)


# ---------------------------------------------------------------------------
# KillTimer called on cleanup
# ---------------------------------------------------------------------------


class TestKillTimer:
    def test_kill_timer_on_cleanup(self, win32, viewer):
        """KillTimer should be called during cleanup."""
        viewer.start()
        viewer.stop()

        win32.user32.KillTimer.assert_called_with(_FAKE_HWND, TIMER_ID)


# ---------------------------------------------------------------------------
# Double start / double stop
# ---------------------------------------------------------------------------


class TestDoubleStartStop:
    def test_double_start_raises(self, win32, viewer):
        """Starting an already-running viewer should raise InvalidStateError."""
        from windowspc_mcp.confinement.errors import InvalidStateError

        _setup_blocking_getmessage(win32)
        viewer.start()
        assert viewer.is_running

        with pytest.raises(InvalidStateError, match="already running"):
            viewer.start()

        viewer.stop()

    def test_double_stop_is_safe(self, win32, viewer):
        """Calling stop() twice should not raise."""
        viewer.start()
        viewer.stop()
        viewer.stop()  # should be a no-op

    def test_stop_without_start_is_safe(self, viewer):
        """Calling stop() before start() should not raise."""
        viewer.stop()


# ---------------------------------------------------------------------------
# stop() posts WM_QUIT to viewer thread
# ---------------------------------------------------------------------------


class TestStopPostsWMQuit:
    def test_stop_posts_wm_quit(self, win32, viewer):
        """stop() should post WM_QUIT to the viewer thread."""
        _setup_blocking_getmessage(win32)
        viewer.start()
        assert viewer._thread_id is not None

        tid = viewer._thread_id
        viewer.stop()

        win32.user32.PostThreadMessageW.assert_called_with(
            tid, WM_QUIT, 0, 0
        )


# ---------------------------------------------------------------------------
# DefWindowProcW for unhandled messages
# ---------------------------------------------------------------------------


class TestDefWindowProc:
    def test_unhandled_message_delegates_to_defwindowproc(self, win32, viewer):
        """Unhandled messages should be passed to DefWindowProcW."""
        viewer.start()
        viewer.stop()

        unknown_msg = 0x9999
        viewer._wndproc(_FAKE_HWND, unknown_msg, 42, 99)

        win32.user32.DefWindowProcW.assert_called_with(
            _FAKE_HWND, unknown_msg, 42, 99
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_blocking_getmessage(win32):
    """Configure GetMessageW to block until PostThreadMessageW sends WM_QUIT."""
    quit_event = threading.Event()

    def fake_post_thread_message(tid, msg, wp, lp):
        if msg == WM_QUIT:
            quit_event.set()
        return True

    win32.user32.PostThreadMessageW.side_effect = fake_post_thread_message

    def fake_getmessage(msg_ptr, hwnd, fmin, fmax):
        quit_event.wait(timeout=5.0)
        return 0  # WM_QUIT

    win32.user32.GetMessageW.side_effect = fake_getmessage
