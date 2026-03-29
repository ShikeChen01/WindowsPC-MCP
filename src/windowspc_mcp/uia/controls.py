"""Window and input control helpers using Win32 APIs."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging

from .core import (
    INPUT,
    INPUT_KEYBOARD,
    INPUT_MOUSE,
    INPUT_UNION,
    KEYBDINPUT,
    KEYEVENTF_KEYUP,
    KEYEVENTF_UNICODE,
    MOUSEEVENTF_ABSOLUTE,
    MOUSEEVENTF_LEFTDOWN,
    MOUSEEVENTF_LEFTUP,
    MOUSEEVENTF_MIDDLEDOWN,
    MOUSEEVENTF_MIDDLEUP,
    MOUSEEVENTF_MOVE,
    MOUSEEVENTF_RIGHTDOWN,
    MOUSEEVENTF_RIGHTUP,
    MOUSEEVENTF_WHEEL,
    MOUSEINPUT,
    GA_ROOT,
    SW_RESTORE,
    WNDENUMPROC,
    send_input,
    user32,
)

log = logging.getLogger(__name__)

# Virtual screen metric IDs
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79


# ---------------------------------------------------------------------------
# Window helpers
# ---------------------------------------------------------------------------


def get_foreground_window() -> int:
    """Return the HWND of the current foreground window."""
    return user32.GetForegroundWindow()


def set_foreground_window(hwnd: int) -> bool:
    """Bring *hwnd* to the foreground.

    Restores the window if it is minimized, then uses the AttachThreadInput
    trick to work around Windows foreground-lock restrictions.
    """
    import ctypes

    SW_SHOW = 5
    SW_SHOWNOACTIVATE = 4

    # Restore if minimized
    if not user32.IsWindowVisible(hwnd):
        user32.ShowWindow(hwnd, SW_SHOW)
    else:
        user32.ShowWindow(hwnd, SW_RESTORE)

    # AttachThreadInput trick
    cur_tid = ctypes.windll.kernel32.GetCurrentThreadId()
    fg_hwnd = user32.GetForegroundWindow()
    fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None)

    if fg_tid and fg_tid != cur_tid:
        user32.AttachThreadInput(cur_tid, fg_tid, True)
        result = bool(user32.SetForegroundWindow(hwnd))
        user32.AttachThreadInput(cur_tid, fg_tid, False)
    else:
        result = bool(user32.SetForegroundWindow(hwnd))

    return result


def get_window_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    """Return (left, top, right, bottom) for the window, or None on failure."""
    rect = ctypes.wintypes.RECT()
    if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return (rect.left, rect.top, rect.right, rect.bottom)
    return None


def move_window(hwnd: int, x: int, y: int, w: int, h: int) -> bool:
    """Move and resize a window."""
    return bool(user32.MoveWindow(hwnd, x, y, w, h, True))


def get_window_title(hwnd: int) -> str:
    """Return the window title text."""
    length = user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def get_window_class(hwnd: int) -> str:
    """Return the window class name."""
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def get_window_pid(hwnd: int) -> int:
    """Return the process ID that owns *hwnd*."""
    pid = ctypes.wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def get_root_window(hwnd: int) -> int:
    """Return the root (top-level) ancestor of *hwnd*."""
    return user32.GetAncestor(hwnd, GA_ROOT)


def is_window_visible(hwnd: int) -> bool:
    """Return True if *hwnd* is visible."""
    return bool(user32.IsWindowVisible(hwnd))


def enumerate_windows() -> list[int]:
    """Return a list of all top-level window HWNDs."""
    hwnds: list[int] = []

    def _cb(hwnd: int, _lparam: int) -> bool:
        hwnds.append(hwnd)
        return True

    cb = WNDENUMPROC(_cb)
    user32.EnumWindows(cb, 0)
    return hwnds


# ---------------------------------------------------------------------------
# Mouse / keyboard input helpers
# ---------------------------------------------------------------------------


def _normalize_coords(x: int, y: int) -> tuple[int, int]:
    """Normalize screen coordinates to the 0-65535 range required by SendInput ABSOLUTE."""
    vx = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    vy = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    vw = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    vh = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)

    # Avoid division by zero on degenerate metrics
    if vw <= 0:
        vw = 1
    if vh <= 0:
        vh = 1

    nx = int((x - vx) * 65535 // vw)
    ny = int((y - vy) * 65535 // vh)
    return nx, ny


def _make_mouse_input(flags: int, dx: int = 0, dy: int = 0, data: int = 0) -> INPUT:
    mi = MOUSEINPUT(
        dx=dx,
        dy=dy,
        mouseData=data,
        dwFlags=flags,
        time=0,
        dwExtraInfo=None,
    )
    return INPUT(type=INPUT_MOUSE, _input=INPUT_UNION(mi=mi))


def _make_key_input(scan: int, flags: int) -> INPUT:
    ki = KEYBDINPUT(
        wVk=0,
        wScan=scan,
        dwFlags=flags,
        time=0,
        dwExtraInfo=None,
    )
    return INPUT(type=INPUT_KEYBOARD, _input=INPUT_UNION(ki=ki))


def click_at(x: int, y: int, button: str = "left", clicks: int = 1) -> None:
    """Click at absolute screen coordinates.

    Uses SendInput with ABSOLUTE flag, normalizing to the virtual screen.
    *button* is one of "left", "right", "middle".
    """
    nx, ny = _normalize_coords(x, y)

    move = _make_mouse_input(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, nx, ny)

    button_map = {
        "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
        "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
        "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
    }
    down_flag, up_flag = button_map.get(button, button_map["left"])

    inputs: list[INPUT] = [move]
    for _ in range(clicks):
        inputs.append(_make_mouse_input(down_flag | MOUSEEVENTF_ABSOLUTE, nx, ny))
        inputs.append(_make_mouse_input(up_flag | MOUSEEVENTF_ABSOLUTE, nx, ny))

    send_input(*inputs)


def type_text(text: str) -> None:
    """Type *text* using Unicode SendInput events."""
    inputs: list[INPUT] = []
    for ch in text:
        scan = ord(ch)
        inputs.append(_make_key_input(scan, KEYEVENTF_UNICODE))
        inputs.append(_make_key_input(scan, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))

    if inputs:
        send_input(*inputs)


def scroll_at(x: int, y: int, amount: int = 3, horizontal: bool = False) -> None:
    """Scroll at coordinates *x*, *y*.

    *amount* is the number of wheel detents (positive = up/right).
    *horizontal* selects horizontal scrolling (MOUSEEVENTF_HWHEEL).
    """
    MOUSEEVENTF_HWHEEL = 0x01000
    WHEEL_DELTA = 120

    user32.SetCursorPos(x, y)

    flag = MOUSEEVENTF_HWHEEL if horizontal else MOUSEEVENTF_WHEEL
    wheel_input = _make_mouse_input(flag, data=amount * WHEEL_DELTA)
    send_input(wheel_input)


def move_cursor(x: int, y: int) -> bool:
    """Move the mouse cursor to absolute screen position *x*, *y*."""
    return bool(user32.SetCursorPos(x, y))
