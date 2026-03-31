"""Tests for windowspc_mcp.desktop.hotkeys — HotkeyService class."""

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
_FAKE_THREAD_ID = 7777

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

MOD_CONTROL = 0x0002
MOD_ALT = 0x0001
VK_SPACE = 0x20
VK_RETURN = 0x0D
VK_CANCEL = 0x03


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def _win32(monkeypatch):
    """Patch all Win32 functions used by the hotkeys module.

    Returns a namespace whose attributes are the mock objects so tests can
    inspect calls and override return values.
    """
    import windowspc_mcp.desktop.hotkeys as mod

    mocks = type("Win32Mocks", (), {})()

    # -- kernel32 --
    mock_kernel32 = MagicMock()
    mock_kernel32.GetCurrentThreadId.return_value = _FAKE_THREAD_ID
    mock_kernel32.GetModuleHandleW.return_value = _FAKE_HINSTANCE
    monkeypatch.setattr(mod, "kernel32", mock_kernel32)
    mocks.kernel32 = mock_kernel32

    # -- ctypes.get_last_error (used instead of kernel32.GetLastError) --
    monkeypatch.setattr(ctypes, "get_last_error", lambda: mocks._last_error)
    mocks._last_error = 0

    # -- user32 --
    mock_user32 = MagicMock()
    mock_user32.RegisterClassW.return_value = _FAKE_ATOM
    mock_user32.CreateWindowExW.return_value = _FAKE_HWND
    mock_user32.RegisterHotKey.return_value = True
    mock_user32.UnregisterHotKey.return_value = True
    mock_user32.DestroyWindow.return_value = True
    mock_user32.UnregisterClassW.return_value = True
    mock_user32.PostThreadMessageW.return_value = True
    mock_user32.DefWindowProcW.return_value = 0
    mock_user32.TranslateMessage.return_value = True
    mock_user32.DispatchMessageW.return_value = 0

    # GetMessageW: return True once (delivering a message), then 0 (WM_QUIT).
    # We'll configure this per-test where needed; default: immediately quit.
    mock_user32.GetMessageW.return_value = 0

    monkeypatch.setattr(mod, "user32", mock_user32)
    mocks.user32 = mock_user32

    return mocks


@pytest.fixture()
def win32(_win32):
    return _win32


@pytest.fixture()
def service():
    """Return a fresh HotkeyService (Win32 calls still need patching)."""
    from windowspc_mcp.desktop.hotkeys import HotkeyService

    return HotkeyService()


@pytest.fixture()
def callbacks():
    """Return a dict of mock callbacks for all three hotkey IDs."""
    from windowspc_mcp.desktop.hotkeys import HotkeyId

    return {
        HotkeyId.TOGGLE: MagicMock(name="on_toggle"),
        HotkeyId.OVERRIDE: MagicMock(name="on_override"),
        HotkeyId.EMERGENCY: MagicMock(name="on_emergency"),
    }


# ---------------------------------------------------------------------------
# Start / stop lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    def test_start_creates_thread_and_registers_hotkeys(self, win32, service, callbacks):
        """start() should create a daemon thread, register the window class,
        create the hidden window, and register all three hotkeys."""
        service.start(callbacks)
        # Let the thread finish (GetMessageW returns 0 immediately → exits)
        service.stop()

        # Window class registered
        win32.user32.RegisterClassW.assert_called_once()

        # Hidden window created
        win32.user32.CreateWindowExW.assert_called_once()

        # Three hotkeys registered
        assert win32.user32.RegisterHotKey.call_count == 3

    def test_start_thread_is_daemon(self, win32, service, callbacks):
        """The listener thread should be a daemon thread."""
        service.start(callbacks)
        assert service._thread is not None
        assert service._thread.daemon is True
        service.stop()

    def test_is_running_reflects_state(self, win32, service, callbacks):
        """is_running should be False before start, True during, False after stop."""
        assert not service.is_running
        # Override GetMessageW to block until we post WM_QUIT
        _setup_blocking_getmessage(win32)
        service.start(callbacks)
        assert service.is_running
        service.stop()
        assert not service.is_running

    def test_start_timeout_raises_hotkey_error(self, win32, service, callbacks):
        """If the listener thread doesn't signal ready within 5s, start() raises."""
        from unittest.mock import patch
        from windowspc_mcp.desktop.hotkeys import HotkeyError

        # Make _listener_main never signal _ready (simulate a hung thread)
        def fake_listener_main():
            pass  # never calls self._ready.set()

        service._listener_main = fake_listener_main

        with patch.object(threading.Event, "wait", return_value=False):
            with pytest.raises(HotkeyError, match="did not become ready"):
                service.start(callbacks)

    def test_stop_is_idempotent(self, win32, service, callbacks):
        """Calling stop() when already stopped should not raise."""
        service.stop()  # never started
        service.stop()  # again

        service.start(callbacks)
        service.stop()
        service.stop()  # already stopped


# ---------------------------------------------------------------------------
# Hotkey registration
# ---------------------------------------------------------------------------


class TestHotkeyRegistration:
    def test_register_hotkey_params(self, win32, service, callbacks):
        """RegisterHotKey should be called with correct modifier+vk for each binding."""
        service.start(callbacks)
        service.stop()

        calls = win32.user32.RegisterHotKey.call_args_list
        # Extract (hwnd, id, modifiers, vk) from each call
        registrations = {c[0][1]: (c[0][2], c[0][3]) for c in calls}

        assert registrations[1] == (MOD_CONTROL | MOD_ALT, VK_SPACE)
        assert registrations[2] == (MOD_CONTROL | MOD_ALT, VK_RETURN)
        assert registrations[3] == (MOD_CONTROL | MOD_ALT, VK_CANCEL)

    def test_register_hotkey_uses_correct_hwnd(self, win32, service, callbacks):
        """All RegisterHotKey calls should use the created HWND."""
        service.start(callbacks)
        service.stop()

        for c in win32.user32.RegisterHotKey.call_args_list:
            assert c[0][0] == _FAKE_HWND

    def test_register_failure_raises_hotkey_error(self, win32, service, callbacks):
        """If RegisterHotKey fails, start() should propagate HotkeyError."""
        from windowspc_mcp.desktop.hotkeys import HotkeyError

        win32.user32.RegisterHotKey.return_value = False
        win32._last_error = 1409  # ERROR_HOTKEY_ALREADY_REGISTERED

        with pytest.raises(HotkeyError, match="RegisterHotKey failed"):
            service.start(callbacks)


# ---------------------------------------------------------------------------
# Unregistration on stop
# ---------------------------------------------------------------------------


class TestUnregistration:
    def test_unregister_all_on_stop(self, win32, service, callbacks):
        """stop() should call UnregisterHotKey for every registered hotkey."""
        service.start(callbacks)
        service.stop()

        assert win32.user32.UnregisterHotKey.call_count == 3
        unregistered_ids = {c[0][1] for c in win32.user32.UnregisterHotKey.call_args_list}
        assert unregistered_ids == {1, 2, 3}

    def test_destroy_window_on_stop(self, win32, service, callbacks):
        """stop() should destroy the hidden message window."""
        service.start(callbacks)
        service.stop()

        win32.user32.DestroyWindow.assert_called_once_with(_FAKE_HWND)

    def test_unregister_class_on_stop(self, win32, service, callbacks):
        """stop() should unregister the window class."""
        service.start(callbacks)
        service.stop()

        win32.user32.UnregisterClassW.assert_called_once()


# ---------------------------------------------------------------------------
# Hotkey dispatch
# ---------------------------------------------------------------------------


class TestHotkeyDispatch:
    def test_wm_hotkey_invokes_callback(self, win32, service, callbacks):
        """When WM_HOTKEY is received, the corresponding callback should fire."""
        from windowspc_mcp.desktop.hotkeys import HotkeyId

        # Configure GetMessageW to deliver one WM_HOTKEY(TOGGLE) then quit.
        call_count = [0]

        def fake_getmessage(msg_ptr, hwnd, fmin, fmax):
            call_count[0] += 1
            if call_count[0] == 1:
                # Modify the service's _msg struct directly (msg_ptr is a
                # CArgObject from ctypes.byref which isn't subscriptable).
                service._msg.message = WM_HOTKEY
                service._msg.wParam = int(HotkeyId.TOGGLE)
                service._msg.lParam = 0
                return 1  # message available
            return 0  # WM_QUIT

        win32.user32.GetMessageW.side_effect = fake_getmessage

        service.start(callbacks)
        # Thread will process one message and then exit.
        service._thread.join(timeout=5.0)

        callbacks[HotkeyId.TOGGLE].assert_called_once()
        callbacks[HotkeyId.OVERRIDE].assert_not_called()
        callbacks[HotkeyId.EMERGENCY].assert_not_called()

    def test_multiple_hotkeys_dispatch(self, win32, service, callbacks):
        """Multiple WM_HOTKEY messages should each invoke the right callback."""
        from windowspc_mcp.desktop.hotkeys import HotkeyId

        call_count = [0]

        def fake_getmessage(msg_ptr, hwnd, fmin, fmax):
            call_count[0] += 1
            if call_count[0] <= 3:
                service._msg.message = WM_HOTKEY
                # Deliver TOGGLE, OVERRIDE, EMERGENCY in order
                service._msg.wParam = call_count[0]
                service._msg.lParam = 0
                return 1
            return 0

        win32.user32.GetMessageW.side_effect = fake_getmessage

        service.start(callbacks)
        service._thread.join(timeout=5.0)

        callbacks[HotkeyId.TOGGLE].assert_called_once()
        callbacks[HotkeyId.OVERRIDE].assert_called_once()
        callbacks[HotkeyId.EMERGENCY].assert_called_once()

    def test_unknown_hotkey_id_does_not_crash(self, win32, service, callbacks):
        """An unknown hotkey ID should be silently ignored."""
        call_count = [0]

        def fake_getmessage(msg_ptr, hwnd, fmin, fmax):
            call_count[0] += 1
            if call_count[0] == 1:
                service._msg.message = WM_HOTKEY
                service._msg.wParam = 999  # unknown ID
                service._msg.lParam = 0
                return 1
            return 0

        win32.user32.GetMessageW.side_effect = fake_getmessage

        service.start(callbacks)
        service._thread.join(timeout=5.0)
        # Should not raise — just log a warning.

    def test_callback_exception_is_caught(self, win32, service, callbacks):
        """If a callback raises, the listener should not crash."""
        from windowspc_mcp.desktop.hotkeys import HotkeyId

        callbacks[HotkeyId.TOGGLE].side_effect = RuntimeError("boom")

        call_count = [0]

        def fake_getmessage(msg_ptr, hwnd, fmin, fmax):
            call_count[0] += 1
            if call_count[0] == 1:
                service._msg.message = WM_HOTKEY
                service._msg.wParam = int(HotkeyId.TOGGLE)
                service._msg.lParam = 0
                return 1
            return 0

        win32.user32.GetMessageW.side_effect = fake_getmessage

        service.start(callbacks)
        service._thread.join(timeout=5.0)
        # Thread should have completed without propagating the exception.
        assert not service._thread.is_alive()


# ---------------------------------------------------------------------------
# Double start rejection
# ---------------------------------------------------------------------------


class TestDoubleStart:
    def test_double_start_raises(self, win32, service, callbacks):
        """Starting an already-running service should raise InvalidStateError."""
        from windowspc_mcp.confinement.errors import InvalidStateError

        _setup_blocking_getmessage(win32)
        service.start(callbacks)
        assert service.is_running

        with pytest.raises(InvalidStateError, match="already running"):
            service.start(callbacks)

        service.stop()

    def test_restart_after_stop_is_allowed(self, win32, service, callbacks):
        """After stop(), starting again should succeed."""
        service.start(callbacks)
        service.stop()

        # Reset mocks so the second start sees fresh state
        win32.user32.RegisterClassW.return_value = _FAKE_ATOM
        win32.user32.CreateWindowExW.return_value = _FAKE_HWND
        win32.user32.RegisterHotKey.return_value = True
        win32.user32.GetMessageW.return_value = 0

        service.start(callbacks)
        service.stop()


# ---------------------------------------------------------------------------
# Thread management
# ---------------------------------------------------------------------------


class TestThreadManagement:
    def test_thread_is_created_and_joined(self, win32, service, callbacks):
        """start() should create a thread; stop() should join it."""
        service.start(callbacks)
        thread = service._thread
        assert thread is not None
        service.stop()
        # After stop, the thread should no longer be alive.
        assert not thread.is_alive()
        assert service._thread is None

    def test_stop_posts_wm_quit(self, win32, service, callbacks):
        """stop() should post WM_QUIT to the listener thread."""
        _setup_blocking_getmessage(win32)
        service.start(callbacks)
        assert service._thread_id is not None

        tid = service._thread_id
        service.stop()

        win32.user32.PostThreadMessageW.assert_called_with(
            tid, WM_QUIT, 0, 0
        )


# ---------------------------------------------------------------------------
# Window creation failure
# ---------------------------------------------------------------------------


class TestWindowCreationFailure:
    def test_register_class_failure(self, win32, service, callbacks):
        from windowspc_mcp.desktop.hotkeys import HotkeyError

        win32.user32.RegisterClassW.return_value = 0
        win32._last_error = 87  # ERROR_INVALID_PARAMETER

        with pytest.raises(HotkeyError, match="RegisterClassW failed"):
            service.start(callbacks)

    def test_register_class_already_exists_is_tolerated(self, win32, service, callbacks):
        """ERROR_CLASS_ALREADY_EXISTS (1410) should be treated as success."""
        win32.user32.RegisterClassW.return_value = 0
        win32._last_error = 1410  # ERROR_CLASS_ALREADY_EXISTS

        # Should NOT raise — class already existing is fine on restart
        service.start(callbacks)
        service.stop()

    def test_create_window_failure(self, win32, service, callbacks):
        from windowspc_mcp.desktop.hotkeys import HotkeyError

        win32.user32.CreateWindowExW.return_value = 0
        win32._last_error = 1400

        with pytest.raises(HotkeyError, match="CreateWindowExW failed"):
            service.start(callbacks)


# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


class TestErrorHierarchy:
    def test_hotkey_error_is_windowsmcp_error(self):
        from windowspc_mcp.confinement.errors import WindowsMCPError
        from windowspc_mcp.desktop.hotkeys import HotkeyError

        assert issubclass(HotkeyError, WindowsMCPError)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_blocking_getmessage(win32):
    """Configure GetMessageW to block until PostThreadMessageW is called.

    This simulates a real message pump: the thread blocks in GetMessageW
    until we post WM_QUIT via stop().
    """
    quit_event = threading.Event()

    original_post = win32.user32.PostThreadMessageW

    def fake_post_thread_message(tid, msg, wp, lp):
        if msg == WM_QUIT:
            quit_event.set()
        return True

    win32.user32.PostThreadMessageW.side_effect = fake_post_thread_message

    def fake_getmessage(msg_ptr, hwnd, fmin, fmax):
        # Block until WM_QUIT is posted.
        quit_event.wait(timeout=5.0)
        return 0  # WM_QUIT

    win32.user32.GetMessageW.side_effect = fake_getmessage
