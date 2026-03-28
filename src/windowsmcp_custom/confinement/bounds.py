"""Display change monitoring via Windows message pump."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import threading
from typing import Callable

WM_DISPLAYCHANGE = 0x007E
WM_WTSSESSION_CHANGE = 0x02B1
WTS_SESSION_LOCK = 0x7
WTS_SESSION_UNLOCK = 0x8

WM_QUIT = 0x0012
HWND_MESSAGE = ctypes.wintypes.HWND(-3)

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32
_wtsapi32 = ctypes.windll.wtsapi32

WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_long,
    ctypes.wintypes.HWND,
    ctypes.c_uint,
    ctypes.wintypes.WPARAM,
    ctypes.wintypes.LPARAM,
)


class DisplayChangeListener:
    """Listens for WM_DISPLAYCHANGE and WTS session change messages.

    Runs a hidden message-only window on a daemon thread.
    """

    def __init__(
        self,
        on_display_change: Callable[[], None] | None = None,
        on_session_change: Callable[[int], None] | None = None,
    ) -> None:
        self._on_display_change = on_display_change
        self._on_session_change = on_session_change
        self._thread: threading.Thread | None = None
        self._hwnd: ctypes.wintypes.HWND | None = None
        self._thread_id: int | None = None

    def start(self) -> None:
        """Start the daemon thread with the message pump."""
        self._thread = threading.Thread(target=self._run, daemon=True, name="DisplayChangeListener")
        self._thread.start()

    def stop(self) -> None:
        """Post WM_QUIT to the message loop and join the thread."""
        if self._thread_id is not None:
            _user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _run(self) -> None:
        """Create a hidden message-only window and run the GetMessage loop."""
        self._thread_id = _kernel32.GetCurrentThreadId()

        # Register a window class
        class_name = "DisplayChangeListenerClass"

        def _wndproc(hwnd: ctypes.wintypes.HWND, msg: int, wparam: int, lparam: int) -> int:
            if msg == WM_DISPLAYCHANGE:
                if self._on_display_change is not None:
                    try:
                        self._on_display_change()
                    except Exception:
                        pass
                return 0
            elif msg == WM_WTSSESSION_CHANGE:
                if self._on_session_change is not None:
                    try:
                        self._on_session_change(wparam)
                    except Exception:
                        pass
                return 0
            return _user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        wndproc_cb = WNDPROC(_wndproc)

        wndclass = ctypes.wintypes.WNDCLASS()
        wndclass.lpfnWndProc = wndproc_cb
        wndclass.hInstance = _kernel32.GetModuleHandleW(None)
        wndclass.lpszClassName = class_name

        atom = _user32.RegisterClassW(ctypes.byref(wndclass))
        if not atom:
            return

        # Create a message-only window
        hwnd = _user32.CreateWindowExW(
            0,
            class_name,
            "DisplayChangeListener",
            0, 0, 0, 0, 0,
            HWND_MESSAGE,
            None,
            _kernel32.GetModuleHandleW(None),
            None,
        )
        if not hwnd:
            return

        self._hwnd = hwnd

        # Register for WTS session notifications
        try:
            _wtsapi32.WTSRegisterSessionNotification(hwnd, 0)
        except Exception:
            pass

        # Run the message loop
        msg = ctypes.wintypes.MSG()
        while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            _user32.TranslateMessage(ctypes.byref(msg))
            _user32.DispatchMessageW(ctypes.byref(msg))

        # Cleanup
        try:
            _wtsapi32.WTSUnRegisterSessionNotification(hwnd)
        except Exception:
            pass
        _user32.DestroyWindow(hwnd)
        _user32.UnregisterClassW(class_name, _kernel32.GetModuleHandleW(None))
