"""Ghost cursor overlay and window conflict detection for COWORK mode.

Provides two components:

1. **GhostCursorOverlay** -- a small, click-through, always-on-top window
   that visualises the non-active actor's cursor position.
2. **ConflictDetector** -- checks whether the human and agent are targeting
   the same window and returns the window title when a conflict is detected.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
from ctypes import POINTER
from enum import Enum

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Win32 constants
# ---------------------------------------------------------------------------

# Extended window styles
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080

# Window styles
WS_POPUP = 0x80000000

# SetWindowPos flags
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

# ShowWindow commands
SW_HIDE = 0
SW_SHOWNOACTIVATE = 4

# HWND_TOPMOST sentinel
HWND_TOPMOST = ctypes.wintypes.HWND(-1)

# SetLayeredWindowAttributes flags
LWA_COLORKEY = 0x00000001

# Colour values (COLORREF = 0x00BBGGRR)
COLOR_TRANSPARENT_KEY = 0x00FF00FF  # Magenta — used as transparent colour key
COLOR_WORKING = 0x00FF0000          # Blue (BGR) — agent actively executing
COLOR_WAITING = 0x00808080          # Gray — agent waiting for gap

# ---------------------------------------------------------------------------
# Win32 structures (reuse WNDCLASSW from hotkeys if available, but we
# declare locally to keep overlay self-contained)
# ---------------------------------------------------------------------------

LRESULT = ctypes.c_ssize_t

WNDPROC = ctypes.WINFUNCTYPE(
    LRESULT,                 # LRESULT (pointer-sized)
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


# ---------------------------------------------------------------------------
# Win32 API bindings
# ---------------------------------------------------------------------------

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

# RegisterClassW
user32.RegisterClassW.restype = ctypes.wintypes.ATOM
user32.RegisterClassW.argtypes = [POINTER(WNDCLASSW)]

# UnregisterClassW
user32.UnregisterClassW.restype = ctypes.wintypes.BOOL
user32.UnregisterClassW.argtypes = [
    ctypes.wintypes.LPCWSTR,
    ctypes.wintypes.HINSTANCE,
]

# CreateWindowExW
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

# DestroyWindow
user32.DestroyWindow.restype = ctypes.wintypes.BOOL
user32.DestroyWindow.argtypes = [ctypes.wintypes.HWND]

# ShowWindow
user32.ShowWindow.restype = ctypes.wintypes.BOOL
user32.ShowWindow.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]

# SetWindowPos
user32.SetWindowPos.restype = ctypes.wintypes.BOOL
user32.SetWindowPos.argtypes = [
    ctypes.wintypes.HWND,   # hWnd
    ctypes.wintypes.HWND,   # hWndInsertAfter
    ctypes.c_int,           # X
    ctypes.c_int,           # Y
    ctypes.c_int,           # cx
    ctypes.c_int,           # cy
    ctypes.wintypes.UINT,   # uFlags
]

# SetLayeredWindowAttributes
user32.SetLayeredWindowAttributes.restype = ctypes.wintypes.BOOL
user32.SetLayeredWindowAttributes.argtypes = [
    ctypes.wintypes.HWND,      # hWnd
    ctypes.wintypes.COLORREF,  # crKey
    ctypes.wintypes.BYTE,      # bAlpha
    ctypes.wintypes.DWORD,     # dwFlags
]

# DefWindowProcW
user32.DefWindowProcW.restype = LRESULT
user32.DefWindowProcW.argtypes = [
    ctypes.wintypes.HWND,
    ctypes.wintypes.UINT,
    ctypes.wintypes.WPARAM,
    ctypes.wintypes.LPARAM,
]

# GetCursorPos
user32.GetCursorPos.restype = ctypes.wintypes.BOOL
user32.GetCursorPos.argtypes = [POINTER(ctypes.wintypes.POINT)]

# WindowFromPoint
user32.WindowFromPoint.restype = ctypes.wintypes.HWND
user32.WindowFromPoint.argtypes = [ctypes.wintypes.POINT]

# GetWindowTextW
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [
    ctypes.wintypes.HWND,
    ctypes.wintypes.LPWSTR,
    ctypes.c_int,
]

# GetDC / ReleaseDC
user32.GetDC.restype = ctypes.wintypes.HDC
user32.GetDC.argtypes = [ctypes.wintypes.HWND]

user32.ReleaseDC.restype = ctypes.c_int
user32.ReleaseDC.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.HDC]

# GDI — CreateSolidBrush, FillRect
gdi32.CreateSolidBrush.restype = ctypes.wintypes.HBRUSH
gdi32.CreateSolidBrush.argtypes = [ctypes.wintypes.COLORREF]

gdi32.DeleteObject.restype = ctypes.wintypes.BOOL
gdi32.DeleteObject.argtypes = [ctypes.wintypes.HANDLE]

user32.FillRect.restype = ctypes.c_int
user32.FillRect.argtypes = [
    ctypes.wintypes.HDC,
    POINTER(ctypes.wintypes.RECT),
    ctypes.wintypes.HBRUSH,
]

# GetModuleHandleW
kernel32.GetModuleHandleW.restype = ctypes.wintypes.HMODULE
kernel32.GetModuleHandleW.argtypes = [ctypes.wintypes.LPCWSTR]

# GetAncestor(HWND, UINT) -> HWND
GA_ROOT = 2
user32.GetAncestor.restype = ctypes.wintypes.HWND
user32.GetAncestor.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.UINT]


# ---------------------------------------------------------------------------
# CursorState enum
# ---------------------------------------------------------------------------

_OVERLAY_WINDOW_CLASS = "WindowsPC_MCP_GhostCursor"


class CursorState(Enum):
    """Visual state for the ghost cursor overlay."""

    WORKING = "working"   # Blue -- agent actively executing
    WAITING = "waiting"   # Gray -- agent waiting for gap
    HIDDEN = "hidden"     # Not visible -- agent has no pending work


# Colour mapping for each visible state (COLORREF)
_STATE_COLORS: dict[CursorState, int] = {
    CursorState.WORKING: COLOR_WORKING,
    CursorState.WAITING: COLOR_WAITING,
}


# ---------------------------------------------------------------------------
# GhostCursorOverlay
# ---------------------------------------------------------------------------


class GhostCursorOverlay:
    """Renders a ghost cursor showing the agent's position.

    The overlay is a small (32x32), click-through, always-on-top window.
    Its colour indicates the agent's state:
    - **WORKING** (blue): the agent is actively executing.
    - **WAITING** (gray): the agent is waiting for a gap.
    - **HIDDEN**: the window is not visible.
    """

    CURSOR_SIZE = 32  # pixels

    def __init__(self) -> None:
        """Initialise but don't create the window yet."""
        self._hwnd: ctypes.wintypes.HWND | None = None
        self._state: CursorState = CursorState.HIDDEN
        self._x: int = 0
        self._y: int = 0
        self._class_atom: int = 0
        # prevent GC of the wndproc callback
        self._wndproc_ref: WNDPROC | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create(self) -> None:
        """Create the overlay window.

        Window style:
        ``WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST | WS_EX_TOOLWINDOW``

        - **LAYERED**: supports transparency via a colour key.
        - **TRANSPARENT**: click-through (doesn't intercept input).
        - **TOPMOST**: always on top of all windows.
        - **TOOLWINDOW**: doesn't appear in the taskbar.
        """
        hinstance = kernel32.GetModuleHandleW(None)

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
        wc.lpszClassName = _OVERLAY_WINDOW_CLASS

        atom = user32.RegisterClassW(ctypes.byref(wc))
        if not atom:
            err = ctypes.get_last_error()
            if err != 1410:  # ERROR_CLASS_ALREADY_EXISTS
                log.error("RegisterClassW failed for '%s', error %d", _OVERLAY_WINDOW_CLASS, err)
                return
        self._class_atom = atom

        ex_style = WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST | WS_EX_TOOLWINDOW
        style = WS_POPUP

        hwnd = user32.CreateWindowExW(
            ex_style,
            _OVERLAY_WINDOW_CLASS,
            "WindowsPC-MCP Ghost Cursor",
            style,
            self._x, self._y,
            self.CURSOR_SIZE, self.CURSOR_SIZE,
            None,   # hWndParent
            None,   # hMenu
            hinstance,
            None,   # lpParam
        )
        if not hwnd:
            err = ctypes.get_last_error()
            log.error("CreateWindowExW failed for ghost cursor, error %d", err)
            return

        self._hwnd = hwnd

        # Set the colour key so the magenta background is transparent.
        user32.SetLayeredWindowAttributes(
            self._hwnd, COLOR_TRANSPARENT_KEY, 0, LWA_COLORKEY,
        )

        # Fill with the transparent colour initially.
        self._fill_color(COLOR_TRANSPARENT_KEY)

        # Start hidden.
        user32.ShowWindow(self._hwnd, SW_HIDE)

        log.debug("Created ghost cursor overlay (HWND %s)", hwnd)

    def move_to(self, x: int, y: int) -> None:
        """Reposition the ghost cursor."""
        self._x = x
        self._y = y
        if self._hwnd is not None:
            flags = SWP_NOACTIVATE
            if self._state is not CursorState.HIDDEN:
                flags |= SWP_SHOWWINDOW
            user32.SetWindowPos(
                self._hwnd,
                HWND_TOPMOST,
                x, y,
                self.CURSOR_SIZE, self.CURSOR_SIZE,
                flags,
            )

    def set_state(self, state: CursorState) -> None:
        """Change visual state. ``HIDDEN`` hides the window."""
        self._state = state
        if self._hwnd is None:
            return

        if state is CursorState.HIDDEN:
            user32.ShowWindow(self._hwnd, SW_HIDE)
        else:
            color = _STATE_COLORS[state]
            self._fill_color(color)
            user32.ShowWindow(self._hwnd, SW_SHOWNOACTIVATE)

    def destroy(self) -> None:
        """Destroy the overlay window. Safe to call multiple times."""
        if self._hwnd is not None:
            user32.DestroyWindow(self._hwnd)
            self._hwnd = None
            log.debug("Destroyed ghost cursor overlay")

        if self._class_atom:
            hinstance = kernel32.GetModuleHandleW(None)
            user32.UnregisterClassW(_OVERLAY_WINDOW_CLASS, hinstance)
            self._class_atom = 0

        self._wndproc_ref = None

    @property
    def position(self) -> tuple[int, int]:
        """Current (x, y) position."""
        return (self._x, self._y)

    @property
    def state(self) -> CursorState:
        """Current visual state."""
        return self._state

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fill_color(self, color: int) -> None:
        """Fill the overlay window with a solid colour."""
        if self._hwnd is None:
            return
        hdc = user32.GetDC(self._hwnd)
        if not hdc:
            return
        try:
            brush = gdi32.CreateSolidBrush(color)
            if brush:
                rect = ctypes.wintypes.RECT(0, 0, self.CURSOR_SIZE, self.CURSOR_SIZE)
                user32.FillRect(hdc, ctypes.byref(rect), brush)
                gdi32.DeleteObject(brush)
        finally:
            user32.ReleaseDC(self._hwnd, hdc)


# ---------------------------------------------------------------------------
# ConflictDetector
# ---------------------------------------------------------------------------


class ConflictDetector:
    """Detects human-agent window targeting conflicts.

    Prevents interleaved input by checking whether the human cursor and the
    agent's intended target position resolve to the same window.
    """

    def __init__(self) -> None:
        """Initialise.  No dependencies."""

    def check_conflict(self, agent_target_x: int, agent_target_y: int) -> str | None:
        """Check if agent's target window conflicts with the human's current window.

        Args:
            agent_target_x: X coordinate where the agent wants to interact.
            agent_target_y: Y coordinate where the agent wants to interact.

        Returns:
            ``None`` if no conflict.
            Window title string if a conflict is detected (for error messaging).
        """
        human_hwnd = self.get_human_window()
        if human_hwnd is None:
            # Cannot determine human position -- assume no conflict.
            return None

        agent_point = ctypes.wintypes.POINT(agent_target_x, agent_target_y)
        agent_hwnd = user32.WindowFromPoint(agent_point)

        if not agent_hwnd:
            return None

        # Normalize to root windows so child/owned windows compare equal.
        human_root = user32.GetAncestor(human_hwnd, GA_ROOT) or human_hwnd
        agent_root = user32.GetAncestor(agent_hwnd, GA_ROOT) or agent_hwnd

        # Compare the two root HWNDs.
        if human_root == agent_root:
            # Conflict! Retrieve the window title.
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(agent_hwnd, buf, 256)
            title = buf.value or "<untitled>"
            log.debug(
                "Conflict detected: human and agent both targeting '%s' (HWND %s)",
                title,
                agent_hwnd,
            )
            return title

        return None

    def get_human_window(self) -> int | None:
        """Get HWND of the window under the human cursor.

        Returns:
            The HWND as an integer, or ``None`` if the cursor position could
            not be determined.
        """
        pt = ctypes.wintypes.POINT()
        ok = user32.GetCursorPos(ctypes.byref(pt))
        if not ok:
            return None
        hwnd = user32.WindowFromPoint(pt)
        if not hwnd:
            return None
        return hwnd
