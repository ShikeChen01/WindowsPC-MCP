"""InputStatus MCP tool — exposes current input system status to the LLM."""

from __future__ import annotations

from windowspc_mcp.desktop.gate import InputGate, InputMode


def register_input_status_tool(gate: InputGate):
    """Returns a tool function that can be registered with FastMCP."""

    async def input_status() -> dict:
        """Check the current input system status.

        Returns the operating mode, whether agent can send input,
        and queue information.
        """
        mode = gate.mode
        return {
            "mode": mode.value,
            "agent_can_input": mode in (InputMode.AGENT_SOLO, InputMode.COWORK),
            "description": _mode_descriptions[mode],
        }

    return input_status


_mode_descriptions = {
    InputMode.AGENT_SOLO: "Agent has full control of its desktop. No scheduling needed.",
    InputMode.COWORK: "Shared desktop. Agent input is scheduled around human activity.",
    InputMode.HUMAN_OVERRIDE: "Human has taken control. Agent input is blocked until released.",
    InputMode.HUMAN_HOME: "User's desktop is active. Agent is paused.",
    InputMode.EMERGENCY_STOP: "Session terminated. No recovery possible.",
}
