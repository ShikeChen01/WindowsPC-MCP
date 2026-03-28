"""App launch tool with window shepherd."""

from __future__ import annotations

import subprocess
import time
from typing import Optional


def register(mcp, *, get_display_manager, get_confinement):
    """Register the App tool."""

    @mcp.tool(
        name="App",
        description=(
            "Launch an application by name, optionally with args or a URL. "
            "The window shepherd waits up to 5 seconds for windows to appear "
            "and moves them to the agent screen. "
            "Returns the count of windows moved."
        ),
    )
    def app(
        name: str,
        args: Optional[list] = None,
        url: Optional[str] = None,
    ) -> str:
        import psutil
        from windowsmcp_custom.uia.controls import (
            enumerate_windows,
            get_window_rect,
            get_window_pid,
            is_window_visible,
            move_window,
        )

        dm = get_display_manager()
        ce = get_confinement()

        agent = dm.agent_display
        if agent is None:
            return "Error: no agent screen — call CreateScreen first."

        # Build the command
        cmd_parts = [name]
        if args:
            cmd_parts.extend(str(a) for a in args)
        if url:
            cmd_parts.append(url)

        cmd = " ".join(cmd_parts)

        try:
            proc = subprocess.Popen(cmd, shell=True)
        except Exception as e:
            return f"Error launching '{cmd}': {e}"

        root_pid = proc.pid

        def _get_pid_tree(root: int) -> set[int]:
            """Return the PID tree rooted at root, best-effort."""
            pids = {root}
            try:
                parent = psutil.Process(root)
                for child in parent.children(recursive=True):
                    pids.add(child.pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            return pids

        center_x = agent.x + agent.width // 2
        center_y = agent.y + agent.height // 2

        moved_hwnds: set[int] = set()
        deadline = time.monotonic() + 5.0

        while time.monotonic() < deadline:
            pids = _get_pid_tree(root_pid)
            for hwnd in enumerate_windows():
                if hwnd in moved_hwnds:
                    continue
                if not is_window_visible(hwnd):
                    continue
                if get_window_pid(hwnd) not in pids:
                    continue
                rect = get_window_rect(hwnd)
                if rect is None:
                    continue
                left, top, right, bottom = rect
                w = right - left
                h = bottom - top
                if w <= 0 or h <= 0:
                    continue
                target_x = center_x - w // 2
                target_y = center_y - h // 2
                move_window(hwnd, target_x, target_y, w, h)
                moved_hwnds.add(hwnd)

            time.sleep(0.1)

        count = len(moved_hwnds)
        return f"Launched '{name}' (PID {root_pid}). Moved {count} window(s) to agent screen."
