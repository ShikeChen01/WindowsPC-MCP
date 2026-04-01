"""InputStatus MCP tool — exposes current input system status to the LLM."""

from __future__ import annotations

from windowspc_mcp.desktop.gate import InputMode


def register(mcp, *, get_gate=None, **kwargs):
    """Register the InputStatus tool."""

    @mcp.tool(
        name="InputStatus",
        description="Check the current input mode and whether the agent can send input.",
    )
    async def InputStatus() -> dict:
        """Check current input mode and whether the agent can send input."""
        gate = get_gate() if callable(get_gate) else None
        if gate is None:
            return {
                "mode": "unknown",
                "agent_can_input": False,
                "description": "Input gate not available",
            }
        mode = gate.mode
        return {
            "mode": mode.value,
            "agent_can_input": mode in (InputMode.AGENT_SOLO, InputMode.COWORK),
            "description": _mode_descriptions.get(mode, "Unknown mode"),
        }


_mode_descriptions = {
    InputMode.AGENT_SOLO: "Agent has full control of its desktop. No scheduling needed.",
    InputMode.COWORK: "Shared desktop. Agent input is scheduled around human activity.",
    InputMode.HUMAN_OVERRIDE: "Human has taken control. Agent input is blocked until released.",
    InputMode.HUMAN_HOME: "User's desktop is active. Agent is paused.",
    InputMode.EMERGENCY_STOP: "Session terminated. No recovery possible.",
}
