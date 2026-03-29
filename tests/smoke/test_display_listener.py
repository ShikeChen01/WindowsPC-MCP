"""Smoke: start and stop a real DisplayChangeListener.

No mocks — exercises the real Win32 message pump thread.
"""

import time


class TestDisplayChangeListenerReal:
    """Start/stop cycle with real thread and Win32 calls."""

    def test_start_and_stop(self):
        from windowspc_mcp.confinement.bounds import DisplayChangeListener

        events = []
        listener = DisplayChangeListener(
            on_display_change=lambda: events.append("display"),
            on_session_change=lambda e: events.append(f"session:{e}"),
        )
        listener.start()
        time.sleep(0.1)  # let the thread create the window
        assert listener._thread is not None
        assert listener._thread.is_alive()

        listener.stop()
        assert listener._thread is None

    def test_double_stop_is_safe(self):
        from windowspc_mcp.confinement.bounds import DisplayChangeListener

        listener = DisplayChangeListener()
        listener.start()
        time.sleep(0.1)
        listener.stop()
        listener.stop()  # should not raise

    def test_stop_without_start(self):
        from windowspc_mcp.confinement.bounds import DisplayChangeListener

        listener = DisplayChangeListener()
        listener.stop()  # should not raise
