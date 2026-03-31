"""Tests for format_gate_error — MCP error response formatting."""

from __future__ import annotations

import pytest

from windowspc_mcp.confinement.errors import (
    AgentPaused,
    AgentPreempted,
    EmergencyStop,
)
from windowspc_mcp.desktop.responses import format_gate_error


# ---------------------------------------------------------------------------
# Correct mapping for each exception type
# ---------------------------------------------------------------------------


class TestFormatGateError:
    def test_agent_preempted(self) -> None:
        result = format_gate_error(AgentPreempted("test"))
        assert result == {
            "error": "HUMAN_OVERRIDE",
            "message": "User has taken control. Retry when released.",
        }

    def test_agent_paused(self) -> None:
        result = format_gate_error(AgentPaused("test"))
        assert result == {
            "error": "AGENT_PAUSED",
            "message": "Agent is paused. Waiting for user to resume.",
        }

    def test_emergency_stop(self) -> None:
        result = format_gate_error(EmergencyStop("test"))
        assert result == {
            "error": "EMERGENCY_STOP",
            "message": "Session terminated by user.",
        }


# ---------------------------------------------------------------------------
# Unknown exceptions are re-raised
# ---------------------------------------------------------------------------


class TestUnknownExceptions:
    def test_runtime_error_reraises(self) -> None:
        with pytest.raises(RuntimeError, match="boom"):
            format_gate_error(RuntimeError("boom"))

    def test_value_error_reraises(self) -> None:
        with pytest.raises(ValueError, match="bad"):
            format_gate_error(ValueError("bad"))

    def test_generic_exception_reraises(self) -> None:
        with pytest.raises(Exception, match="generic"):
            format_gate_error(Exception("generic"))
