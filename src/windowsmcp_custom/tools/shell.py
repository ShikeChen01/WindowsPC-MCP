"""Shell tool: PowerShell."""

from __future__ import annotations

import subprocess


def register(mcp, *, get_display_manager, get_confinement, get_state_manager=None, get_guard=None, get_input_service=None):
    """Register the PowerShell tool."""

    @mcp.tool(
        name="PowerShell",
        description=(
            "Run a PowerShell command and return its output. "
            "timeout: seconds to wait before terminating (clamped to [1, 120], default 30)."
        ),
    )
    def power_shell(command: str, timeout: int = 30) -> str:
        guard = get_guard() if get_guard is not None else None
        if guard:
            err = guard.check("PowerShell")
            if err:
                return err

        timeout = max(1, min(120, int(timeout)))

        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = result.stdout
            errors = result.stderr
            if errors:
                output = output + "\n[stderr]\n" + errors if output else "[stderr]\n" + errors
            return output.strip() if output else f"(exit code {result.returncode}, no output)"
        except subprocess.TimeoutExpired:
            return f"Error: command timed out after {timeout}s."
        except Exception as e:
            return f"Error: {e}"
