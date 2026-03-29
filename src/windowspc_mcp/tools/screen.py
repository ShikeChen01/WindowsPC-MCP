"""Screen management tools: CreateScreen, DestroyScreen, ScreenInfo, RecoverWindow."""

from __future__ import annotations

import re

from windowspc_mcp.confinement.decorators import guarded_tool, with_tool_name


def register(mcp, *, get_display_manager, get_confinement, get_state_manager=None, get_guard=None, get_input_service=None):
    """Register screen management tools."""

    @mcp.tool(
        name="CreateScreen",
        description=(
            "Create a virtual agent display. "
            "width is clamped to [1280, 1920], height to [720, 1080]. "
            "Raises an error if an agent screen already exists."
        ),
    )
    def create_screen(width: int = 1920, height: int = 1080) -> str:
        dm = get_display_manager()
        ce = get_confinement()

        width = max(1280, min(1920, width))
        height = max(720, min(1080, height))

        display = dm.create_display(width, height)
        ce.set_agent_bounds(display)

        # Transition to READY now that display + bounds are configured
        if get_state_manager is not None:
            sm = get_state_manager()
            if sm is not None:
                from windowspc_mcp.server import ServerState
                sm.transition(ServerState.READY)

        return (
            f"Agent screen created: {display.device_name} "
            f"at ({display.x}, {display.y}) {display.width}x{display.height}"
        )

    @mcp.tool(
        name="DestroyScreen",
        description="Destroy the current agent virtual display and release its bounds.",
    )
    def destroy_screen() -> str:
        dm = get_display_manager()
        ce = get_confinement()

        dm.destroy_display()
        ce.clear_bounds()

        # Transition back from READY to DRIVER_AVAILABLE (represented as INIT after driver check)
        # We use DEGRADED with reason to indicate "display destroyed but driver present"
        if get_state_manager is not None:
            sm = get_state_manager()
            if sm is not None:
                from windowspc_mcp.server import ServerState
                # Only transition away from READY — leave DEGRADED/DRIVER_MISSING alone
                if sm.state == ServerState.READY:
                    sm.transition(
                        ServerState.DEGRADED,
                        reason="agent screen destroyed — call CreateScreen to re-enable GUI tools",
                    )

        return "Agent screen destroyed."

    @mcp.tool(
        name="ScreenInfo",
        description=(
            "List all monitors currently active on the system. "
            "The agent screen (if any) is marked with [AGENT]."
        ),
    )
    def screen_info() -> str:
        dm = get_display_manager()
        ce = get_confinement()

        monitors = dm.enumerate_monitors()
        if not monitors:
            return "No monitors found."

        agent_display = dm.agent_display
        lines = []
        for i, mon in enumerate(monitors):
            is_agent = agent_display is not None and mon.device_name == agent_display.device_name
            tag = " [AGENT]" if is_agent else ""
            lines.append(
                f"[{i}] {mon.device_name}{tag}: "
                f"({mon.x}, {mon.y}) {mon.width}x{mon.height}"
            )

        return "\n".join(lines)

    @mcp.tool(
        name="RecoverWindow",
        description=(
            "Find windows matching one or more selectors and move them onto the agent screen. "
            "Selectors: title (regex string), pid (int), process_name (str), class_name (str). "
            "Returns an error if more than 5 windows match to prevent accidental bulk moves."
        ),
    )
    @guarded_tool(get_guard)
    @with_tool_name("RecoverWindow")
    def recover_window(
        title: str = None,
        pid: int = None,
        process_name: str = None,
        class_name: str = None,
    ) -> str:
        from windowspc_mcp.uia.controls import (
            enumerate_windows,
            get_window_rect,
            get_window_title,
            get_window_class,
            get_window_pid,
            is_window_visible,
            move_window,
        )

        dm = get_display_manager()
        ce = get_confinement()

        agent = dm.agent_display
        if agent is None:
            return "Error: no agent screen — call CreateScreen first."

        title_re = re.compile(title, re.IGNORECASE) if title else None
        matches = []

        for hwnd in enumerate_windows():
            if not is_window_visible(hwnd):
                continue

            if title_re is not None:
                wt = get_window_title(hwnd)
                if not title_re.search(wt):
                    continue

            if pid is not None:
                if get_window_pid(hwnd) != pid:
                    continue

            if process_name is not None:
                try:
                    import psutil
                    wp = get_window_pid(hwnd)
                    proc = psutil.Process(wp)
                    if process_name.lower() not in proc.name().lower():
                        continue
                except Exception:
                    continue

            if class_name is not None:
                wc = get_window_class(hwnd)
                if class_name.lower() not in wc.lower():
                    continue

            matches.append(hwnd)

        if not matches:
            return "No matching windows found."

        if len(matches) > 5:
            return (
                f"Error: {len(matches)} windows matched — too many to move safely. "
                "Narrow your selectors (max 5 allowed)."
            )

        center_x = agent.x + agent.width // 2
        center_y = agent.y + agent.height // 2

        moved = 0
        for hwnd in matches:
            rect = get_window_rect(hwnd)
            if rect is None:
                continue
            left, top, right, bottom = rect
            w = right - left
            h = bottom - top
            target_x = center_x - w // 2
            target_y = center_y - h // 2
            move_window(hwnd, target_x, target_y, w, h)
            moved += 1

        return f"Moved {moved} window(s) to agent screen center ({center_x}, {center_y})."
