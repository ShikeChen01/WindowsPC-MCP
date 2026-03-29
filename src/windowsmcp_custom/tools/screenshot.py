"""Screenshot tools: Screenshot, Snapshot."""

from __future__ import annotations


def register(mcp, *, get_display_manager, get_confinement, get_state_manager=None, get_guard=None):
    """Register screenshot tools."""

    @mcp.tool(
        name="Screenshot",
        description=(
            "Capture a screenshot. "
            "screen: 'agent' (default) captures the agent display, "
            "'all' captures every monitor, "
            "or an integer index to capture that specific monitor. "
            "Returns base64-encoded JPEG image(s)."
        ),
    )
    def screenshot(screen: str = "agent") -> list:
        guard = get_guard() if get_guard is not None else None
        if guard:
            err = guard.check("Screenshot")
            if err:
                return err

        from windowsmcp_custom.display.capture import capture_region, image_to_base64

        dm = get_display_manager()

        def _capture_one(mon) -> dict:
            img = capture_region(mon.left, mon.top, mon.right, mon.bottom)
            b64 = image_to_base64(img)
            return {
                "type": "image",
                "data": b64,
                "description": (
                    f"{mon.device_name} ({mon.width}x{mon.height} at {mon.x},{mon.y})"
                    + (" [AGENT]" if getattr(mon, "is_agent", False) else "")
                ),
            }

        if screen == "agent":
            agent = dm.agent_display
            if agent is None:
                return [{"type": "text", "data": "Error: no agent screen — call CreateScreen first."}]
            img_entry = _capture_one(agent)
            return [img_entry, {"type": "text", "data": img_entry["description"]}]

        elif screen == "all":
            monitors = dm.enumerate_monitors()
            if not monitors:
                return [{"type": "text", "data": "No monitors found."}]
            results = []
            agent = dm.agent_display
            for mon in monitors:
                if agent is not None and mon.device_name == agent.device_name:
                    mon.is_agent = True
                entry = _capture_one(mon)
                results.append(entry)
                results.append({"type": "text", "data": entry["description"]})
            return results

        else:
            # Try numeric index
            try:
                idx = int(screen)
            except (ValueError, TypeError):
                return [{"type": "text", "data": f"Error: unknown screen value '{screen}'. Use 'agent', 'all', or an integer index."}]

            monitors = dm.enumerate_monitors()
            if idx < 0 or idx >= len(monitors):
                return [{"type": "text", "data": f"Error: monitor index {idx} out of range (0–{len(monitors)-1})."}]

            mon = monitors[idx]
            agent = dm.agent_display
            if agent is not None and mon.device_name == agent.device_name:
                mon.is_agent = True
            entry = _capture_one(mon)
            return [entry, {"type": "text", "data": entry["description"]}]

    @mcp.tool(
        name="Snapshot",
        description=(
            "Capture a screenshot and list visible windows with titles, positions, and class names. "
            "screen: same as Screenshot — 'agent' (default), 'all', or monitor index. "
            "Window positions are agent-relative when capturing the agent screen."
        ),
    )
    def snapshot(screen: str = "agent") -> list:
        guard = get_guard() if get_guard is not None else None
        if guard:
            err = guard.check("Snapshot")
            if err:
                return err

        from windowsmcp_custom.display.capture import capture_region, image_to_base64
        from windowsmcp_custom.uia.controls import (
            enumerate_windows,
            get_window_rect,
            get_window_title,
            get_window_class,
            is_window_visible,
        )

        dm = get_display_manager()

        def _capture_one(mon) -> dict:
            img = capture_region(mon.left, mon.top, mon.right, mon.bottom)
            b64 = image_to_base64(img)
            return {
                "type": "image",
                "data": b64,
                "description": (
                    f"{mon.device_name} ({mon.width}x{mon.height} at {mon.x},{mon.y})"
                    + (" [AGENT]" if getattr(mon, "is_agent", False) else "")
                ),
            }

        def _window_list(reference_mon=None) -> str:
            """Build a text summary of visible windows, up to 30 entries."""
            windows = []
            for hwnd in enumerate_windows():
                if not is_window_visible(hwnd):
                    continue
                rect = get_window_rect(hwnd)
                if rect is None:
                    continue
                left, top, right, bottom = rect
                w = right - left
                h = bottom - top
                title = get_window_title(hwnd) or "(no title)"
                cls = get_window_class(hwnd)

                if reference_mon is not None:
                    # Check if window center is on this monitor
                    cx, cy = left + w // 2, top + h // 2
                    if not reference_mon.contains_point(cx, cy):
                        continue
                    # Convert to monitor-relative coords
                    rx, ry = reference_mon.to_relative(left, top)
                    pos_str = f"rel({rx},{ry}) {w}x{h}"
                else:
                    pos_str = f"abs({left},{top}) {w}x{h}"

                windows.append(f"  [{len(windows)+1}] {title!r} cls={cls!r} pos={pos_str}")
                if len(windows) >= 30:
                    windows.append("  ... (capped at 30 entries)")
                    break

            if not windows:
                return "  (no visible windows)"
            return "\n".join(windows)

        agent = dm.agent_display

        if screen == "agent":
            if agent is None:
                return [{"type": "text", "data": "Error: no agent screen — call CreateScreen first."}]
            agent.is_agent = True
            img_entry = _capture_one(agent)
            win_text = "Windows on agent screen:\n" + _window_list(agent)
            return [img_entry, {"type": "text", "data": img_entry["description"]}, {"type": "text", "data": win_text}]

        elif screen == "all":
            monitors = dm.enumerate_monitors()
            if not monitors:
                return [{"type": "text", "data": "No monitors found."}]
            results = []
            for mon in monitors:
                if agent is not None and mon.device_name == agent.device_name:
                    mon.is_agent = True
                entry = _capture_one(mon)
                win_text = f"Windows on {mon.device_name}:\n" + _window_list(mon)
                results.extend([entry, {"type": "text", "data": entry["description"]}, {"type": "text", "data": win_text}])
            return results

        else:
            try:
                idx = int(screen)
            except (ValueError, TypeError):
                return [{"type": "text", "data": f"Error: unknown screen value '{screen}'."}]

            monitors = dm.enumerate_monitors()
            if idx < 0 or idx >= len(monitors):
                return [{"type": "text", "data": f"Error: monitor index {idx} out of range."}]

            mon = monitors[idx]
            if agent is not None and mon.device_name == agent.device_name:
                mon.is_agent = True
            entry = _capture_one(mon)
            win_text = f"Windows on {mon.device_name}:\n" + _window_list(mon)
            return [entry, {"type": "text", "data": entry["description"]}, {"type": "text", "data": win_text}]
