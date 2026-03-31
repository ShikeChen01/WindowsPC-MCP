"""MCP-friendly error response formatting for InputGate exceptions."""

from __future__ import annotations

from windowspc_mcp.confinement.errors import (
    AgentPaused,
    AgentPreempted,
    EmergencyStop,
)


def format_gate_error(error: Exception) -> dict:
    """Convert InputGate exceptions to MCP tool response dicts.

    AgentPreempted -> {"error": "HUMAN_OVERRIDE", "message": "..."}
    AgentPaused    -> {"error": "AGENT_PAUSED",   "message": "..."}
    EmergencyStop  -> {"error": "EMERGENCY_STOP", "message": "..."}

    Other exceptions are re-raised (not our concern).
    """
    if isinstance(error, AgentPreempted):
        return {
            "error": "HUMAN_OVERRIDE",
            "message": "User has taken control. Retry when released.",
        }
    if isinstance(error, AgentPaused):
        return {
            "error": "AGENT_PAUSED",
            "message": "Agent is paused. Waiting for user to resume.",
        }
    if isinstance(error, EmergencyStop):
        return {
            "error": "EMERGENCY_STOP",
            "message": "Session terminated by user.",
        }
    raise error
