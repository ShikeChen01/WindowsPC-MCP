"""Shell tool: PowerShell."""

from __future__ import annotations

import subprocess

from windowsmcp_custom.confinement.decorators import guarded_tool, with_tool_name


def register(mcp, *, get_display_manager, get_confinement, get_state_manager=None, get_guard=None, get_input_service=None):
    """Register the PowerShell tool."""

    @mcp.tool(
        name="PowerShell",
        description=(
            "Run a PowerShell command and return its output. "
            "timeout: seconds to wait before terminating (clamped to [1, 120], default 30)."
        ),
    )
    @guarded_tool(get_guard)
    @with_tool_name("PowerShell")
    def power_shell(command: str, timeout: int = 30) -> str:
        timeout = max(1, min(120, int(timeout)))

        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-OutputFormat", "Text", "-Command", command],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
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
