"""AgentInputService — rich input delivery for the agent's virtual display.

Provides click-with-focus, typing with caret/clear/enter, text escaping,
and shortcut execution with filtering. All coordinates are absolute
(already translated by confinement engine).
"""

import logging
import time
import re

from windowsmcp_custom.uia.controls import (
    click_at, type_text as raw_type_text, scroll_at, move_cursor,
    set_foreground_window, get_foreground_window, get_window_rect,
    enumerate_windows, is_window_visible,
)
from windowsmcp_custom.uia.core import (
    INPUT, INPUT_UNION, KEYBDINPUT, MOUSEINPUT,
    INPUT_MOUSE, INPUT_KEYBOARD,
    MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP,
    KEYEVENTF_KEYUP, send_input,
)
from windowsmcp_custom.confinement.errors import BlockedShortcutError, TargetNotFoundError
from windowsmcp_custom.confinement.shortcuts import is_shortcut_allowed, get_blocked_reason

logger = logging.getLogger(__name__)

# Virtual key codes
VK_CTRL = 0x11
VK_SHIFT = 0x10
VK_ALT = 0x12
VK_RETURN = 0x0D
VK_HOME = 0x24
VK_END = 0x23
VK_BACK = 0x08
VK_A = 0x41

VK_MAP: dict[str, int] = {
    "ctrl": VK_CTRL, "alt": VK_ALT, "shift": VK_SHIFT,
    "enter": VK_RETURN, "escape": 0x1B, "tab": 0x09,
    "backspace": VK_BACK, "delete": 0x2E,
    "home": VK_HOME, "end": VK_END,
    "pageup": 0x21, "pagedown": 0x22,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "space": 0x20,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
}

# Characters that need escaping for SendKeys-style input
_SENDKEYS_SPECIAL = set("{}[]()^+%~")


def _make_vk_input(vk: int, flags: int = 0) -> INPUT:
    """Create a keyboard INPUT structure from a virtual key code."""
    ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=None)
    return INPUT(type=INPUT_KEYBOARD, _input=INPUT_UNION(ki=ki))


def _parse_vk(key: str) -> int:
    """Convert a key name to a virtual key code."""
    k = key.strip().lower()
    if k in VK_MAP:
        return VK_MAP[k]
    if len(key) == 1:
        return ord(key.upper())
    raise ValueError(f"Unknown key: {key!r}")


def _escape_text(text: str) -> str:
    """Escape special characters for safe text input."""
    return "".join(f"{{{c}}}" if c in _SENDKEYS_SPECIAL else c for c in text)


class AgentInputService:
    """High-level input operations for the agent's virtual display.

    All coordinate parameters are ABSOLUTE screen coordinates
    (already translated by the confinement engine).
    """

    def __init__(self, agent_bounds_fn):
        """
        Args:
            agent_bounds_fn: callable returning current ScreenBounds or None
        """
        self._get_bounds = agent_bounds_fn

    def _find_foreground_on_agent_screen(self) -> int | None:
        """Find the foreground window on the agent's screen."""
        bounds = self._get_bounds()
        if bounds is None:
            return None
        hwnd = get_foreground_window()
        if hwnd:
            rect = get_window_rect(hwnd)
            if rect:
                cx = (rect[0] + rect[2]) // 2
                cy = (rect[1] + rect[3]) // 2
                if bounds.left <= cx < bounds.right and bounds.top <= cy < bounds.bottom:
                    return hwnd
        return None

    def _find_window_at(self, abs_x: int, abs_y: int) -> int | None:
        """Find the topmost visible window at the given absolute coordinates."""
        for hwnd in enumerate_windows():
            if not is_window_visible(hwnd):
                continue
            rect = get_window_rect(hwnd)
            if rect and rect[0] <= abs_x < rect[2] and rect[1] <= abs_y < rect[3]:
                return hwnd
        return None

    def _ensure_focus(self, abs_x: int, abs_y: int) -> None:
        """Try to ensure the window at (abs_x, abs_y) has focus."""
        hwnd = self._find_window_at(abs_x, abs_y)
        if hwnd:
            current = get_foreground_window()
            if current != hwnd:
                set_foreground_window(hwnd)
                time.sleep(0.05)

    def click(
        self, abs_x: int, abs_y: int,
        button: str = "left", clicks: int = 1,
    ) -> str:
        """Click at absolute coordinates with focus acquisition."""
        self._ensure_focus(abs_x, abs_y)
        click_at(abs_x, abs_y, button, clicks)
        return f"Clicked ({abs_x}, {abs_y}) [{button} x{clicks}]"

    def type_text(
        self, text: str,
        abs_x: int | None = None, abs_y: int | None = None,
        clear: bool = False,
        caret_position: str = "idle",
        press_enter: bool = False,
    ) -> str:
        """Type text with rich input semantics.

        Args:
            text: Text to type
            abs_x, abs_y: Optional click-to-focus position (absolute)
            clear: If True, Ctrl+A then Delete before typing
            caret_position: 'start' (Home), 'end' (End), or 'idle' (no change)
            press_enter: If True, press Enter after typing
        """
        # Click to focus if position given
        if abs_x is not None and abs_y is not None:
            self._ensure_focus(abs_x, abs_y)
            click_at(abs_x, abs_y, "left", 1)
            time.sleep(0.1)

        # Position caret
        if caret_position == "start":
            send_input(_make_vk_input(VK_HOME), _make_vk_input(VK_HOME, KEYEVENTF_KEYUP))
            time.sleep(0.05)
        elif caret_position == "end":
            send_input(_make_vk_input(VK_END), _make_vk_input(VK_END, KEYEVENTF_KEYUP))
            time.sleep(0.05)

        # Clear existing content
        if clear:
            time.sleep(0.1)
            # Ctrl+A
            send_input(
                _make_vk_input(VK_CTRL), _make_vk_input(VK_A),
                _make_vk_input(VK_A, KEYEVENTF_KEYUP), _make_vk_input(VK_CTRL, KEYEVENTF_KEYUP),
            )
            time.sleep(0.05)
            # Backspace to delete
            send_input(_make_vk_input(VK_BACK), _make_vk_input(VK_BACK, KEYEVENTF_KEYUP))
            time.sleep(0.05)

        # Type the text
        raw_type_text(text)

        # Press enter if requested
        if press_enter:
            time.sleep(0.05)
            send_input(_make_vk_input(VK_RETURN), _make_vk_input(VK_RETURN, KEYEVENTF_KEYUP))

        parts = []
        if abs_x is not None:
            parts.append(f"at ({abs_x}, {abs_y})")
        if clear:
            parts.append("cleared first")
        if caret_position != "idle":
            parts.append(f"caret={caret_position}")
        if press_enter:
            parts.append("pressed Enter")
        detail = f" ({', '.join(parts)})" if parts else ""
        return f"Typed {len(text)} chars{detail}"

    def scroll(
        self, abs_x: int, abs_y: int,
        amount: int = -3, horizontal: bool = False,
    ) -> str:
        """Scroll at absolute coordinates."""
        scroll_at(abs_x, abs_y, amount, horizontal)
        direction = "horizontally" if horizontal else "vertically"
        return f"Scrolled {direction} by {amount} at ({abs_x}, {abs_y})"

    def move(self, abs_x: int, abs_y: int, drag: bool = False) -> str:
        """Move cursor, optionally dragging."""
        if drag:
            mi_down = MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=MOUSEEVENTF_LEFTDOWN, time=0, dwExtraInfo=None)
            send_input(INPUT(type=INPUT_MOUSE, _input=INPUT_UNION(mi=mi_down)))

        move_cursor(abs_x, abs_y)

        if drag:
            mi_up = MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=MOUSEEVENTF_LEFTUP, time=0, dwExtraInfo=None)
            send_input(INPUT(type=INPUT_MOUSE, _input=INPUT_UNION(mi=mi_up)))

        return f"{'Dragged' if drag else 'Moved'} to ({abs_x}, {abs_y})"

    def send_shortcut(self, keys: str) -> str:
        """Send a keyboard shortcut with filtering."""
        if not is_shortcut_allowed(keys):
            raise BlockedShortcutError(get_blocked_reason(keys))

        parts = [p.strip() for p in keys.split("+") if p.strip()]
        vk_codes = [_parse_vk(p) for p in parts]

        inputs = []
        for vk in vk_codes:
            inputs.append(_make_vk_input(vk, 0))
        for vk in reversed(vk_codes):
            inputs.append(_make_vk_input(vk, KEYEVENTF_KEYUP))
        send_input(*inputs)

        return f"Sent shortcut: {keys}"
