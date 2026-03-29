"""Multi-action tools: MultiSelect, MultiEdit."""

from __future__ import annotations

import time

from windowsmcp_custom.confinement.decorators import guarded_tool, with_tool_name


def register(mcp, *, get_display_manager, get_confinement, get_state_manager=None, get_guard=None, get_input_service=None):
    """Register multi-action tools."""

    @mcp.tool(
        name="MultiSelect",
        description=(
            "Click multiple positions in sequence. "
            "positions: list of [x, y] pairs (agent-relative). "
            "button: 'left' (default), 'right', or 'middle'. "
            "Stops immediately on the first ConfinementError."
        ),
    )
    @guarded_tool(get_guard)
    @with_tool_name("MultiSelect")
    def multi_select(positions: list, button: str = "left") -> str:
        ce = get_confinement()
        svc = get_input_service()
        clicked = 0
        for pos in positions:
            if len(pos) < 2:
                continue
            abs_x, abs_y = ce.validate_and_translate(pos[0], pos[1])
            svc.click(abs_x, abs_y, button, 1)
            clicked += 1
            time.sleep(0.1)
        return f"Clicked {clicked} positions"

    @mcp.tool(
        name="MultiEdit",
        description=(
            "Click and type into multiple fields in sequence. "
            "fields: list of dicts with 'x', 'y', 'text' keys (agent-relative). "
            "Stops immediately on the first error."
        ),
    )
    @guarded_tool(get_guard)
    @with_tool_name("MultiEdit")
    def multi_edit(fields: list) -> str:
        from windowsmcp_custom.uia.controls import click_at, type_text
        from windowsmcp_custom.confinement.engine import ConfinementError

        ce = get_confinement()
        done = 0

        for i, field in enumerate(fields):
            try:
                x = int(field["x"])
                y = int(field["y"])
                text = str(field["text"])
                abs_x, abs_y = ce.validate_and_translate(x, y)
                click_at(abs_x, abs_y, "left", 1)
                type_text(text)
                done += 1
            except ConfinementError as e:
                return f"Completed {done}/{len(fields)} fields. Stopped at field {i+1}: {e}"
            except (KeyError, TypeError, ValueError) as e:
                return f"Completed {done}/{len(fields)} fields. Bad field spec at index {i}: {e}"
            except Exception as e:
                return f"Completed {done}/{len(fields)} fields. Error at field {i+1}: {e}"

        return f"Completed {done}/{len(fields)} fields."
