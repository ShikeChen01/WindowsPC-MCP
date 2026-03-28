"""Multi-action tools: MultiSelect, MultiEdit."""

from __future__ import annotations

import time


def register(mcp, *, get_display_manager, get_confinement):
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
    def multi_select(positions: list, button: str = "left") -> str:
        from windowsmcp_custom.uia.controls import click_at
        from windowsmcp_custom.confinement.engine import ConfinementError

        ce = get_confinement()
        clicked = 0

        for pos in positions:
            try:
                x, y = int(pos[0]), int(pos[1])
                abs_x, abs_y = ce.validate_and_translate(x, y)
                click_at(abs_x, abs_y, button, 1)
                clicked += 1
                time.sleep(0.1)
            except ConfinementError as e:
                return f"Clicked {clicked}/{len(positions)} positions. Stopped: {e}"
            except Exception as e:
                return f"Clicked {clicked}/{len(positions)} positions. Error at position {clicked+1}: {e}"

        return f"Clicked {clicked}/{len(positions)} positions."

    @mcp.tool(
        name="MultiEdit",
        description=(
            "Click and type into multiple fields in sequence. "
            "fields: list of dicts with 'x', 'y', 'text' keys (agent-relative). "
            "Stops immediately on the first error."
        ),
    )
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
