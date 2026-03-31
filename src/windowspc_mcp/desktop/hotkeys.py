"""Hotkey service for mode-toggle shortcuts.

Registers global hotkeys via ``RegisterHotKey`` on a hidden message-only
window and dispatches ``WM_HOTKEY`` events to registered callbacks from a
dedicated listener thread.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import threading
from ctypes import POINTER
from enum import IntEnum
from typing import Callable

from windowspc_mcp.confinement.errors import InvalidStateError, WindowsMCPError

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom errors
# ---------------------------------------------------------------------------


class HotkeyError(WindowsMCPError):
    """Failure in hotkey registration, dispatch, or teardown."""


# ---------------------------------------------------------------------------
# Win32 constants
# ---------------------------------------------------------------------------

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002

VK_SPACE = 0x20
VK_RETURN = 0x0D
VK_CANCEL = 0x03  # Break key

# HWND_MESSAGE — parent for message-only windows
HWND_MESSAGE = ctypes.wintypes.HWND(-3)

# ---------------------------------------------------------------------------
# Win32 structures
# ---------------------------------------------------------------------------

WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_long,           # LRESULT
    ctypes.wintypes.HWND,    # hWnd
    ctypes.wintypes.UINT,    # uMsg
    ctypes.wintypes.WPARAM,  # wParam
    ctypes.wintypes.LPARAM,  # lParam
)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", ctypes.wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", ctypes.wintypes.HINSTANCE),
        ("hIcon", ctypes.wintypes.HICON),
        ("hCursor", ctypes.wintypes.HANDLE),
        ("hbrBackground", ctypes.wintypes.HANDLE),
        ("lpszMenuName", ctypes.wintypes.LPCWSTR),
        ("lpszClassName", ctypes.wintypes.LPCWSTR),
    ]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.wintypes.HWND),
        ("message", ctypes.wintypes.UINT),
        ("wParam", ctypes.wintypes.WPARAM),
        ("lParam", ctypes.wintypes.LPARAM),
        ("time", ctypes.wintypes.DWORD),
        ("pt", ctypes.wintypes.POINT),
    ]


# ---------------------------------------------------------------------------
# Win32 API bindings — user32
# ---------------------------------------------------------------------------

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# RegisterHotKey(HWND, int, UINT, UINT) -> BOOL
user32.RegisterHotKey.restype = ctypes.wintypes.BOOL
user32.RegisterHotKey.argtypes = [
    ctypes.wintypes.HWND,   # hWnd
    ctypes.c_int,           # id
    ctypes.wintypes.UINT,   # fsModifiers
    ctypes.wintypes.UINT,   # vk
]

# UnregisterHotKey(HWND, int) -> BOOL
user32.UnregisterHotKey.restype = ctypes.wintypes.BOOL
user32.UnregisterHotKey.argtypes = [
    ctypes.wintypes.HWND,   # hWnd
    ctypes.c_int,           # id
]

# RegisterClassW(WNDCLASSW*) -> ATOM (WORD)
user32.RegisterClassW.restype = ctypes.wintypes.ATOM
user32.RegisterClassW.argtypes = [POINTER(WNDCLASSW)]

# UnregisterClassW(LPCWSTR, HINSTANCE) -> BOOL
user32.UnregisterClassW.restype = ctypes.wintypes.BOOL
user32.UnregisterClassW.argtypes = [
    ctypes.wintypes.LPCWSTR,
    ctypes.wintypes.HINSTANCE,
]

# CreateWindowExW(...) -> HWND
user32.CreateWindowExW.restype = ctypes.wintypes.HWND
user32.CreateWindowExW.argtypes = [
    ctypes.wintypes.DWORD,    # dwExStyle
    ctypes.wintypes.LPCWSTR,  # lpClassName
    ctypes.wintypes.LPCWSTR,  # lpWindowName
    ctypes.wintypes.DWORD,    # dwStyle
    ctypes.c_int,             # x
    ctypes.c_int,             # y
    ctypes.c_int,             # nWidth
    ctypes.c_int,             # nHeight
    ctypes.wintypes.HWND,     # hWndParent
    ctypes.wintypes.HMENU,    # hMenu
    ctypes.wintypes.HINSTANCE,  # hInstance
    ctypes.c_void_p,          # lpParam
]

# DestroyWindow(HWND) -> BOOL
user32.DestroyWindow.restype = ctypes.wintypes.BOOL
user32.DestroyWindow.argtypes = [ctypes.wintypes.HWND]

# GetMessageW(MSG*, HWND, UINT, UINT) -> BOOL
user32.GetMessageW.restype = ctypes.wintypes.BOOL
user32.GetMessageW.argtypes = [
    POINTER(MSG),
    ctypes.wintypes.HWND,
    ctypes.wintypes.UINT,
    ctypes.wintypes.UINT,
]

# TranslateMessage(MSG*) -> BOOL
user32.TranslateMessage.restype = ctypes.wintypes.BOOL
user32.TranslateMessage.argtypes = [POINTER(MSG)]

# DispatchMessageW(MSG*) -> LRESULT (c_long)
user32.DispatchMessageW.restype = ctypes.c_long
user32.DispatchMessageW.argtypes = [POINTER(MSG)]

# PostThreadMessageW(DWORD, UINT, WPARAM, LPARAM) -> BOOL
user32.PostThreadMessageW.restype = ctypes.wintypes.BOOL
user32.PostThreadMessageW.argtypes = [
    ctypes.wintypes.DWORD,   # idThread
    ctypes.wintypes.UINT,    # Msg
    ctypes.wintypes.WPARAM,  # wParam
    ctypes.wintypes.LPARAM,  # lParam
]

# DefWindowProcW(HWND, UINT, WPARAM, LPARAM) -> LRESULT
user32.DefWindowProcW.restype = ctypes.c_long
user32.DefWindowProcW.argtypes = [
    ctypes.wintypes.HWND,
    ctypes.wintypes.UINT,
    ctypes.wintypes.WPARAM,
    ctypes.wintypes.LPARAM,
]

# GetModuleHandleW(LPCWSTR) -> HMODULE
kernel32.GetModuleHandleW.restype = ctypes.wintypes.HMODULE
kernel32.GetModuleHandleW.argtypes = [ctypes.wintypes.LPCWSTR]

# GetCurrentThreadId() -> DWORD
kernel32.GetCurrentThreadId.restype = ctypes.wintypes.DWORD
kernel32.GetCurrentThreadId.argtypes = []

# GetLastError() -> DWORD
kernel32.GetLastError.restype = ctypes.wintypes.DWORD
kernel32.GetLastError.argtypes = []

# ---------------------------------------------------------------------------
# Hotkey definitions
# ---------------------------------------------------------------------------

_WINDOW_CLASS_NAME = "WindowsPC_MCP_Hotkey"


class HotkeyId(IntEnum):
    """Identifiers for registered hotkeys."""
    TOGGLE = 1       # Ctrl+Alt+Space — cycle through modes
    OVERRIDE = 2     # Ctrl+Alt+Enter — instant HUMAN_OVERRIDE
    EMERGENCY = 3    # Ctrl+Alt+Break  — EMERGENCY_STOP


# (modifiers, virtual-key) for each hotkey
_HOTKEY_BINDINGS: dict[HotkeyId, tuple[int, int]] = {
    HotkeyId.TOGGLE:    (MOD_CONTROL | MOD_ALT, VK_SPACE),
    HotkeyId.OVERRIDE:  (MOD_CONTROL | MOD_ALT, VK_RETURN),
    HotkeyId.EMERGENCY: (MOD_CONTROL | MOD_ALT, VK_CANCEL),
}


# ---------------------------------------------------------------------------
# HotkeyService
# ---------------------------------------------------------------------------


class HotkeyService:
    """Register system-wide hotkeys and dispatch callbacks from a listener thread.

    Usage::

        svc = HotkeyService()
        svc.start({
            HotkeyId.TOGGLE:    on_toggle,
            HotkeyId.OVERRIDE:  on_override,
            HotkeyId.EMERGENCY: on_emergency,
        })
        ...
        svc.stop()
    """

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._hwnd: ctypes.wintypes.HWND | None = None
        self._callbacks: dict[HotkeyId, Callable[[], None]] = {}
        self._registered_ids: list[int] = []
        self._ready = threading.Event()
        self._error: Exception | None = None
        # prevent WNDPROC callback from being garbage-collected
        self._wndproc_ref: WNDPROC | None = None
        self._class_atom: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, callbacks: dict[HotkeyId, Callable[[], None]]) -> None:
        """Start the hotkey listener thread and register hotkeys.

        Args:
            callbacks: Maps each :class:`HotkeyId` to a zero-arg callable
                       invoked when that hotkey fires.

        Raises:
            InvalidStateError: If the service is already running.
            HotkeyError: If hotkey registration fails.
        """
        if self._thread is not None and self._thread.is_alive():
            raise InvalidStateError("HotkeyService is already running")

        self._callbacks = dict(callbacks)
        self._ready.clear()
        self._error = None

        self._thread = threading.Thread(
            target=self._listener_main,
            name="hotkey-listener",
            daemon=True,
        )
        self._thread.start()

        # Wait for the listener thread to finish registration.
        self._ready.wait(timeout=5.0)
        if self._error is not None:
            raise self._error

    def stop(self) -> None:
        """Unregister hotkeys, destroy the hidden window, and stop the listener.

        Safe to call multiple times (idempotent).
        """
        if self._thread is None or not self._thread.is_alive():
            # Already stopped or never started — reset state and return.
            self._thread = None
            self._thread_id = None
            return

        # Send WM_QUIT to the listener thread's message queue.
        if self._thread_id is not None:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)

        self._thread.join(timeout=5.0)
        self._thread = None
        self._thread_id = None

    @property
    def is_running(self) -> bool:
        """``True`` if the listener thread is active."""
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------
    # Listener thread
    # ------------------------------------------------------------------

    def _listener_main(self) -> None:
        """Entry point for the listener daemon thread.

        1. Record the thread ID (for PostThreadMessageW).
        2. Create a hidden message-only window.
        3. Register all hotkeys on that window.
        4. Signal the caller that setup is done.
        5. Run the message pump until WM_QUIT.
        6. Unregister hotkeys and destroy the window.
        """
        self._thread_id = kernel32.GetCurrentThreadId()

        try:
            self._create_message_window()
            self._register_hotkeys()
        except Exception as exc:
            self._error = exc
            self._ready.set()
            self._cleanup()
            return

        # Signal that we're ready.
        self._ready.set()

        # -- message pump --
        self._msg = MSG()
        while True:
            ret = user32.GetMessageW(ctypes.byref(self._msg), None, 0, 0)
            if ret == 0 or ret == -1:
                # WM_QUIT (0) or error (-1) — exit the loop.
                break
            if self._msg.message == WM_HOTKEY:
                self._dispatch_hotkey(int(self._msg.wParam))
            user32.TranslateMessage(ctypes.byref(self._msg))
            user32.DispatchMessageW(ctypes.byref(self._msg))

        self._cleanup()

    def _create_message_window(self) -> None:
        """Register a window class and create a hidden message-only window."""
        hinstance = kernel32.GetModuleHandleW(None)

        # Default window procedure — we don't process anything besides WM_HOTKEY
        # which we handle in the message loop, not in the WndProc.
        self._wndproc_ref = WNDPROC(
            lambda hwnd, msg, wp, lp: user32.DefWindowProcW(hwnd, msg, wp, lp)
        )

        wc = WNDCLASSW()
        wc.style = 0
        wc.lpfnWndProc = self._wndproc_ref
        wc.cbClsExtra = 0
        wc.cbWndExtra = 0
        wc.hInstance = hinstance
        wc.hIcon = None
        wc.hCursor = None
        wc.hbrBackground = None
        wc.lpszMenuName = None
        wc.lpszClassName = _WINDOW_CLASS_NAME

        atom = user32.RegisterClassW(ctypes.byref(wc))
        if not atom:
            err = kernel32.GetLastError()
            raise HotkeyError(
                f"RegisterClassW failed for '{_WINDOW_CLASS_NAME}', error {err}"
            )
        self._class_atom = atom

        hwnd = user32.CreateWindowExW(
            0,                    # dwExStyle
            _WINDOW_CLASS_NAME,   # lpClassName
            "WindowsPC-MCP Hotkey Sink",  # lpWindowName
            0,                    # dwStyle
            0, 0, 0, 0,          # x, y, w, h
            HWND_MESSAGE,         # hWndParent — message-only
            None,                 # hMenu
            hinstance,            # hInstance
            None,                 # lpParam
        )
        if not hwnd:
            err = kernel32.GetLastError()
            raise HotkeyError(
                f"CreateWindowExW failed, error {err}"
            )
        self._hwnd = hwnd
        log.debug("Created hidden message window (HWND %s)", hwnd)

    def _register_hotkeys(self) -> None:
        """Register all configured hotkeys on the hidden window."""
        assert self._hwnd is not None
        for hk_id, (modifiers, vk) in _HOTKEY_BINDINGS.items():
            ok = user32.RegisterHotKey(self._hwnd, int(hk_id), modifiers, vk)
            if not ok:
                err = kernel32.GetLastError()
                raise HotkeyError(
                    f"RegisterHotKey failed for {hk_id.name} "
                    f"(id={hk_id}, mod=0x{modifiers:04X}, vk=0x{vk:02X}), "
                    f"error {err}"
                )
            self._registered_ids.append(int(hk_id))
            log.debug(
                "Registered hotkey %s (id=%d, mod=0x%04X, vk=0x%02X)",
                hk_id.name, hk_id, modifiers, vk,
            )

    def _dispatch_hotkey(self, hotkey_id: int) -> None:
        """Invoke the callback for *hotkey_id*, if registered."""
        try:
            hk = HotkeyId(hotkey_id)
        except ValueError:
            log.warning("Received unknown hotkey id %d", hotkey_id)
            return

        cb = self._callbacks.get(hk)
        if cb is not None:
            try:
                cb()
            except Exception:
                log.exception("Hotkey callback for %s raised", hk.name)
        else:
            log.debug("No callback registered for hotkey %s", hk.name)

    def _cleanup(self) -> None:
        """Unregister hotkeys, destroy window, unregister class."""
        if self._hwnd:
            for hk_id in self._registered_ids:
                user32.UnregisterHotKey(self._hwnd, hk_id)
            self._registered_ids.clear()

            user32.DestroyWindow(self._hwnd)
            self._hwnd = None
            log.debug("Destroyed hidden message window")

        if self._class_atom:
            hinstance = kernel32.GetModuleHandleW(None)
            user32.UnregisterClassW(_WINDOW_CLASS_NAME, hinstance)
            self._class_atom = 0

        self._wndproc_ref = None
