"""Tests for windowspc_mcp.confinement.bounds — DisplayChangeListener.

DisplayChangeListener depends heavily on Win32 ctypes (RegisterClassW, CreateWindowExW,
message pumps). We test the public API surface using mocks to avoid requiring a real
Windows message loop in CI.
"""

import threading
from unittest.mock import MagicMock, patch

import pytest

from windowspc_mcp.confinement.bounds import (
    DisplayChangeListener,
    WM_DISPLAYCHANGE,
    WM_QUIT,
    WM_WTSSESSION_CHANGE,
    WTS_SESSION_LOCK,
    WTS_SESSION_UNLOCK,
    HWND_MESSAGE,
)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestDisplayChangeListenerInit:
    def test_default_callbacks_are_none(self):
        listener = DisplayChangeListener()
        assert listener._on_display_change is None
        assert listener._on_session_change is None

    def test_accepts_callbacks(self):
        on_change = MagicMock()
        on_session = MagicMock()
        listener = DisplayChangeListener(
            on_display_change=on_change,
            on_session_change=on_session,
        )
        assert listener._on_display_change is on_change
        assert listener._on_session_change is on_session

    def test_initial_state(self):
        listener = DisplayChangeListener()
        assert listener._thread is None
        assert listener._hwnd is None
        assert listener._thread_id is None


# ---------------------------------------------------------------------------
# start() creates a daemon thread
# ---------------------------------------------------------------------------


class TestDisplayChangeListenerStart:
    @patch("windowspc_mcp.confinement.bounds._user32")
    @patch("windowspc_mcp.confinement.bounds._kernel32")
    @patch("windowspc_mcp.confinement.bounds._wtsapi32")
    def test_start_creates_daemon_thread(self, mock_wts, mock_kernel, mock_user):
        # Make the message loop exit immediately
        mock_user.RegisterClassW.return_value = 0  # atom=0 causes _run to return early

        listener = DisplayChangeListener()
        listener.start()
        assert listener._thread is not None
        assert listener._thread.daemon is True
        assert listener._thread.name == "DisplayChangeListener"
        listener._thread.join(timeout=2)


# ---------------------------------------------------------------------------
# stop() posts WM_QUIT
# ---------------------------------------------------------------------------


class TestDisplayChangeListenerStop:
    def test_stop_without_start_is_safe(self):
        listener = DisplayChangeListener()
        listener.stop()  # should not raise

    @patch("windowspc_mcp.confinement.bounds._user32")
    def test_stop_posts_quit_message(self, mock_user):
        listener = DisplayChangeListener()
        listener._thread_id = 12345
        mock_thread = MagicMock()
        listener._thread = mock_thread

        listener.stop()

        mock_user.PostThreadMessageW.assert_called_once_with(12345, WM_QUIT, 0, 0)
        mock_thread.join.assert_called_once_with(timeout=5)
        # stop() sets self._thread = None after join
        assert listener._thread is None

    def test_stop_clears_thread_ref(self):
        listener = DisplayChangeListener()
        mock_thread = MagicMock()
        listener._thread = mock_thread
        listener._thread_id = None  # no thread_id means no PostThreadMessage
        listener.stop()
        assert listener._thread is None


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestBoundsConstants:
    def test_wm_displaychange_value(self):
        assert WM_DISPLAYCHANGE == 0x007E

    def test_wm_wtssession_change_value(self):
        assert WM_WTSSESSION_CHANGE == 0x02B1

    def test_wts_session_lock_value(self):
        assert WTS_SESSION_LOCK == 0x7

    def test_wts_session_unlock_value(self):
        assert WTS_SESSION_UNLOCK == 0x8

    def test_wm_quit_value(self):
        assert WM_QUIT == 0x0012
