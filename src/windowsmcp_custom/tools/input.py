"""Input tools: Click, Type, Move, Scroll, Shortcut, Wait."""

from __future__ import annotations

import time

from windowsmcp_custom.confinement.decorators import guarded_tool, with_tool_name


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
    @guarded_tool(get_guard)
    @with_tool_name("Click")
    def click(x: int, y: int, button: str = "left", clicks: int = 1) -> str:
        ce = get_confinement()
        abs_x, abs_y = ce.validate_and_translate(x, y)
        svc = get_input_service()
        return svc.click(abs_x, abs_y, button, clicks)

    @mcp.tool(
        name="Type",
        description=(
            "Type text, optionally clicking at (x, y) first. "
            "clear: replace existing content. "
            "caret_position: 'start'/'end'/'idle'. "
            "press_enter: submit after typing."
        ),
    )
    @guarded_tool(get_guard)
    @with_tool_name("Type")
    def type_tool(
        text: str,
        x: int = None,
        y: int = None,
        clear: bool = False,
        caret_position: str = "idle",
        press_enter: bool = False,
    ) -> str:
        ce = get_confinement()
        abs_x = abs_y = None
        if x is not None and y is not None:
            abs_x, abs_y = ce.validate_and_translate(x, y)
        if isinstance(clear, str):
            clear = clear.lower() in ("true", "1", "yes")
        if isinstance(press_enter, str):
            press_enter = press_enter.lower() in ("true", "1", "yes")
        svc = get_input_service()
        return svc.type_text(text, abs_x, abs_y, clear=clear, caret_position=caret_position, press_enter=press_enter)

    @mcp.tool(
        name="Move",
        description=(
            "Move the mouse cursor to agent-relative coordinates (x, y). "
            "drag: if True, hold left button down during the move."
        ),
    )
    @guarded_tool(get_guard)
    @with_tool_name("Move")
    def move(x: int, y: int, drag: bool = False) -> str:
        ce = get_confinement()
        abs_x, abs_y = ce.validate_and_translate(x, y)
        if isinstance(drag, str):
            drag = drag.lower() in ("true", "1", "yes")
        svc = get_input_service()
        return svc.move(abs_x, abs_y, drag=drag)

    @mcp.tool(
        name="Scroll",
        description=(
            "Scroll at agent-relative coordinates (x, y). "
            "amount: wheel detents, negative = down/left (default -3). "
            "horizontal: if True, scroll horizontally."
        ),
    )
    @guarded_tool(get_guard)
    @with_tool_name("Scroll")
    def scroll(x: int, y: int, amount: int = -3, horizontal: bool = False) -> str:
        ce = get_confinement()
        abs_x, abs_y = ce.validate_and_translate(x, y)
        if isinstance(horizontal, str):
            horizontal = horizontal.lower() in ("true", "1", "yes")
        svc = get_input_service()
        return svc.scroll(abs_x, abs_y, amount, horizontal)

    @mcp.tool(
        name="Shortcut",
        description=(
            "Send a keyboard shortcut. "
            "keys: plus-separated key names, e.g. 'ctrl+c', 'alt+f4', 'f5'. "
            "Blocked shortcuts (e.g. win+l, alt+tab) are rejected."
        ),
    )
    @guarded_tool(get_guard)
    @with_tool_name("Shortcut")
    def shortcut(keys: str) -> str:
        svc = get_input_service()
        return svc.send_shortcut(keys)  # raises BlockedShortcutError if blocked — caught by decorator

    @mcp.tool(
        name="Wait",
        description="Pause execution for the specified number of seconds (clamped to [0.1, 30]).",
    )
    @guarded_tool(get_guard)
    @with_tool_name("Wait")
    def wait(seconds: float = 1.0) -> str:
        seconds = max(0.1, min(30.0, float(seconds)))
        time.sleep(seconds)
        return f"Waited {seconds:.2f}s."
