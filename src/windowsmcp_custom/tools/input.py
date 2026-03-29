"""Input tools: Click, Type, Move, Scroll, Shortcut, Wait."""

from __future__ import annotations

import time

from windowsmcp_custom.confinement.decorators import guarded_tool, with_tool_name


def register(mcp, *, get_display_manager, get_confinement, get_state_manager=None, get_guard=None, get_input_service=None):
    """Register input tools."""

    @mcp.tool(
        name="Click",
        description=(
            "Click at agent-relative coordinates (x, y), or by element label from Snapshot. "
            "label: integer element ID from Snapshot's Interactive/Scrollable Elements list; "
            "if provided, x/y are ignored and coordinates are resolved from the latest tree state. "
            "button: 'left' (default), 'right', or 'middle'. "
            "clicks: number of clicks (default 1)."
        ),
    )
    @guarded_tool(get_guard)
    @with_tool_name("Click")
    def click(x: int = None, y: int = None, button: str = "left", clicks: int = 1, label: int = None) -> str:
        ce = get_confinement()
        if label is not None:
            dm = get_display_manager()
            tree_state = getattr(dm, "_latest_tree_state", None)
            if tree_state is None:
                return "Error: no tree state available — call Snapshot first."
            try:
                abs_x, abs_y = tree_state.get_coordinates_from_label(label)
            except IndexError as e:
                return f"Error: {e}"
            # Translate absolute coords to agent-relative for confinement validation
            agent = dm.agent_display
            if agent is not None:
                rel_x, rel_y = agent.to_relative(abs_x, abs_y)
            else:
                rel_x, rel_y = abs_x, abs_y
            abs_x, abs_y = ce.validate_and_translate(rel_x, rel_y)
        else:
            if x is None or y is None:
                return "Error: either label or both x and y must be provided."
            abs_x, abs_y = ce.validate_and_translate(x, y)
        svc = get_input_service()
        return svc.click(abs_x, abs_y, button, clicks)

    @mcp.tool(
        name="Type",
        description=(
            "Type text, optionally clicking at (x, y) or an element label first. "
            "label: integer element ID from Snapshot's Interactive Elements list; "
            "if provided, x/y are ignored and coordinates are resolved from the latest tree state. "
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
        label: int = None,
    ) -> str:
        ce = get_confinement()
        abs_x = abs_y = None
        if label is not None:
            dm = get_display_manager()
            tree_state = getattr(dm, "_latest_tree_state", None)
            if tree_state is None:
                return "Error: no tree state available — call Snapshot first."
            try:
                lx, ly = tree_state.get_coordinates_from_label(label)
            except IndexError as e:
                return f"Error: {e}"
            agent = dm.agent_display
            if agent is not None:
                rel_x, rel_y = agent.to_relative(lx, ly)
            else:
                rel_x, rel_y = lx, ly
            abs_x, abs_y = ce.validate_and_translate(rel_x, rel_y)
        elif x is not None and y is not None:
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
