"""Input tools: Click, Type, Move, Scroll, Shortcut, Wait."""

from __future__ import annotations

import time


# Virtual key codes
VK_MAP: dict[str, int] = {
    "ctrl": 0x11,
    "alt": 0x12,
    "shift": 0x10,
    "enter": 0x0D,
    "escape": 0x1B,
    "tab": 0x09,
    "backspace": 0x08,
    "delete": 0x2E,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "space": 0x20,
    "f1": 0x70,
    "f2": 0x71,
    "f3": 0x72,
    "f4": 0x73,
    "f5": 0x74,
    "f6": 0x75,
    "f7": 0x76,
    "f8": 0x77,
    "f9": 0x78,
    "f10": 0x79,
    "f11": 0x7A,
    "f12": 0x7B,
}


def _parse_vk(key: str) -> int:
    """Convert a key name to a virtual key code."""
    key_lower = key.lower().strip()
    if key_lower in VK_MAP:
        return VK_MAP[key_lower]
    if len(key) == 1:
        return ord(key.upper())
    raise ValueError(f"Unknown key: {key!r}")


def register(mcp, *, get_display_manager, get_confinement, get_state_manager=None, get_guard=None, get_input_service=None):
    """Register input tools."""

    @mcp.tool(
        name="Click",
        description=(
            "Click at agent-relative coordinates (x, y). "
            "button: 'left' (default), 'right', or 'middle'. "
            "clicks: number of clicks (default 1)."
        ),
    )
    def click(x: int, y: int, button: str = "left", clicks: int = 1) -> str:
        guard = get_guard() if get_guard is not None else None
        if guard:
            err = guard.check("Click")
            if err:
                return err

        from windowsmcp_custom.uia.controls import click_at

        ce = get_confinement()
        abs_x, abs_y = ce.validate_and_translate(x, y)
        click_at(abs_x, abs_y, button, clicks)
        return f"Clicked ({x}, {y}) [{button} x{clicks}]"

    @mcp.tool(
        name="Type",
        description=(
            "Type text, optionally clicking at (x, y) first. "
            "clear: if True (or 'true'), select-all before typing to replace existing content."
        ),
    )
    def type_tool(
        text: str,
        x: int = None,
        y: int = None,
        clear: bool = False,
    ) -> str:
        guard = get_guard() if get_guard is not None else None
        if guard:
            err = guard.check("Type")
            if err:
                return err

        from windowsmcp_custom.uia.controls import click_at, type_text
        from windowsmcp_custom.uia.core import (
            INPUT,
            INPUT_UNION,
            KEYBDINPUT,
            INPUT_KEYBOARD,
            send_input,
        )

        # Normalise clear param (allow string "true"/"false")
        if isinstance(clear, str):
            clear = clear.lower() in ("true", "1", "yes")

        ce = get_confinement()

        if x is not None and y is not None:
            abs_x, abs_y = ce.validate_and_translate(x, y)
            click_at(abs_x, abs_y, "left", 1)

        if clear:
            # Send Ctrl+A via SendInput using VK codes (not unicode path)
            VK_CTRL = 0x11
            VK_A = 0x41
            KEYEVENTF_KEYUP = 0x0002

            def _make_vk_input(vk: int, flags: int) -> INPUT:
                ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=None)
                return INPUT(type=INPUT_KEYBOARD, _input=INPUT_UNION(ki=ki))

            send_input(
                _make_vk_input(VK_CTRL, 0),
                _make_vk_input(VK_A, 0),
                _make_vk_input(VK_A, KEYEVENTF_KEYUP),
                _make_vk_input(VK_CTRL, KEYEVENTF_KEYUP),
            )

        type_text(text)
        loc = f" at ({x}, {y})" if x is not None and y is not None else ""
        clear_note = " (cleared first)" if clear else ""
        return f"Typed {len(text)} character(s){loc}{clear_note}."

    @mcp.tool(
        name="Move",
        description=(
            "Move the mouse cursor to agent-relative coordinates (x, y). "
            "drag: if True, hold left button down during the move."
        ),
    )
    def move(x: int, y: int, drag: bool = False) -> str:
        guard = get_guard() if get_guard is not None else None
        if guard:
            err = guard.check("Move")
            if err:
                return err

        from windowsmcp_custom.uia.controls import move_cursor
        from windowsmcp_custom.uia.core import (
            INPUT,
            INPUT_UNION,
            MOUSEINPUT,
            INPUT_MOUSE,
            MOUSEEVENTF_LEFTDOWN,
            MOUSEEVENTF_LEFTUP,
            send_input,
        )

        ce = get_confinement()
        abs_x, abs_y = ce.validate_and_translate(x, y)

        if drag:
            # Press left button down
            mi_down = MOUSEINPUT(
                dx=0, dy=0, mouseData=0,
                dwFlags=MOUSEEVENTF_LEFTDOWN,
                time=0, dwExtraInfo=None,
            )
            send_input(INPUT(type=INPUT_MOUSE, _input=INPUT_UNION(mi=mi_down)))

        move_cursor(abs_x, abs_y)

        if drag:
            mi_up = MOUSEINPUT(
                dx=0, dy=0, mouseData=0,
                dwFlags=MOUSEEVENTF_LEFTUP,
                time=0, dwExtraInfo=None,
            )
            send_input(INPUT(type=INPUT_MOUSE, _input=INPUT_UNION(mi=mi_up)))

        drag_note = " (drag)" if drag else ""
        return f"Moved cursor to ({x}, {y}){drag_note}."

    @mcp.tool(
        name="Scroll",
        description=(
            "Scroll at agent-relative coordinates (x, y). "
            "amount: wheel detents, negative = down/left (default -3). "
            "horizontal: if True, scroll horizontally."
        ),
    )
    def scroll(x: int, y: int, amount: int = -3, horizontal: bool = False) -> str:
        guard = get_guard() if get_guard is not None else None
        if guard:
            err = guard.check("Scroll")
            if err:
                return err

        from windowsmcp_custom.uia.controls import scroll_at

        ce = get_confinement()
        abs_x, abs_y = ce.validate_and_translate(x, y)
        scroll_at(abs_x, abs_y, amount, horizontal)
        direction = "horizontal" if horizontal else "vertical"
        return f"Scrolled {direction} at ({x}, {y}) by {amount}."

    @mcp.tool(
        name="Shortcut",
        description=(
            "Send a keyboard shortcut. "
            "keys: plus-separated key names, e.g. 'ctrl+c', 'alt+f4', 'f5'. "
            "Blocked shortcuts (e.g. win+l, alt+tab) are rejected."
        ),
    )
    def shortcut(keys: str) -> str:
        guard = get_guard() if get_guard is not None else None
        if guard:
            err = guard.check("Shortcut")
            if err:
                return err

        from windowsmcp_custom.confinement.shortcuts import is_shortcut_allowed, get_blocked_reason
        from windowsmcp_custom.uia.core import (
            INPUT,
            INPUT_UNION,
            KEYBDINPUT,
            INPUT_KEYBOARD,
            KEYEVENTF_KEYUP,
            send_input,
        )

        if not is_shortcut_allowed(keys):
            reason = get_blocked_reason(keys)
            return f"Error: shortcut '{keys}' is blocked — {reason}"

        parts = [p.strip() for p in keys.split("+") if p.strip()]

        vk_codes: list[int] = []
        for part in parts:
            try:
                vk_codes.append(_parse_vk(part))
            except ValueError as e:
                return f"Error: {e}"

        KEYEVENTF_EXTENDEDKEY = 0x0001

        def _make_vk_input(vk: int, flags: int) -> INPUT:
            ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=None)
            return INPUT(type=INPUT_KEYBOARD, _input=INPUT_UNION(ki=ki))

        inputs = []
        # Key down sequence
        for vk in vk_codes:
            inputs.append(_make_vk_input(vk, 0))
        # Key up in reverse order
        for vk in reversed(vk_codes):
            inputs.append(_make_vk_input(vk, KEYEVENTF_KEYUP))

        send_input(*inputs)
        return f"Sent shortcut: {keys}"

    @mcp.tool(
        name="Wait",
        description="Pause execution for the specified number of seconds (clamped to [0.1, 30]).",
    )
    def wait(seconds: float = 1.0) -> str:
        guard = get_guard() if get_guard is not None else None
        if guard:
            err = guard.check("Wait")
            if err:
                return err

        seconds = max(0.1, min(30.0, float(seconds)))
        time.sleep(seconds)
        return f"Waited {seconds:.2f}s."
