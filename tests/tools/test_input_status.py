"""Tests for InputStatus tool — exposes current input system status."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from windowspc_mcp.desktop.gate import InputGate, InputMode
from windowspc_mcp.tools.input_status import register, _mode_descriptions


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def gate() -> InputGate:
    return InputGate()


@pytest.fixture()
def input_status(gate: InputGate):
    """Register InputStatus on a mock MCP and return the tool function."""
    mock_mcp = MagicMock()
    # Capture the function passed to @mcp.tool()
    captured = {}

    def tool_decorator(**kwargs):
        def wrapper(fn):
            captured["fn"] = fn
            return fn
        return wrapper

    mock_mcp.tool = tool_decorator
    register(mock_mcp, get_gate=lambda: gate)
    return captured["fn"]


def _run(coro):
    """Helper to run an async function synchronously."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# No gate available
# ---------------------------------------------------------------------------


class TestNoGate:
    def test_returns_unknown_when_no_gate(self) -> None:
        mock_mcp = MagicMock()
        captured = {}

        def tool_decorator(**kwargs):
            def wrapper(fn):
                captured["fn"] = fn
                return fn
            return wrapper

        mock_mcp.tool = tool_decorator
        register(mock_mcp, get_gate=None)
        result = _run(captured["fn"]())
        assert result["mode"] == "unknown"
        assert result["agent_can_input"] is False
        assert "not available" in result["description"]


# ---------------------------------------------------------------------------
# Correct status for each mode
# ---------------------------------------------------------------------------


class TestInputStatusPerMode:
    def test_agent_solo(self, gate: InputGate, input_status) -> None:
        gate.set_mode(InputMode.AGENT_SOLO)
        result = _run(input_status())
        assert result["mode"] == "agent_solo"
        assert result["agent_can_input"] is True
        assert result["description"] == _mode_descriptions[InputMode.AGENT_SOLO]

    def test_cowork(self, gate: InputGate, input_status) -> None:
        gate.set_mode(InputMode.COWORK)
        result = _run(input_status())
        assert result["mode"] == "cowork"
        assert result["agent_can_input"] is True
        assert result["description"] == _mode_descriptions[InputMode.COWORK]

    def test_human_override(self, gate: InputGate, input_status) -> None:
        gate.set_mode(InputMode.HUMAN_OVERRIDE)
        result = _run(input_status())
        assert result["mode"] == "human_override"
        assert result["agent_can_input"] is False
        assert result["description"] == _mode_descriptions[InputMode.HUMAN_OVERRIDE]

    def test_human_home(self, gate: InputGate, input_status) -> None:
        # Default mode
        result = _run(input_status())
        assert result["mode"] == "human_home"
        assert result["agent_can_input"] is False
        assert result["description"] == _mode_descriptions[InputMode.HUMAN_HOME]

    def test_emergency_stop(self, gate: InputGate, input_status) -> None:
        gate.set_mode(InputMode.EMERGENCY_STOP)
        result = _run(input_status())
        assert result["mode"] == "emergency_stop"
        assert result["agent_can_input"] is False
        assert result["description"] == _mode_descriptions[InputMode.EMERGENCY_STOP]


# ---------------------------------------------------------------------------
# agent_can_input is True only for AGENT_SOLO and COWORK
# ---------------------------------------------------------------------------


class TestAgentCanInput:
    @pytest.mark.parametrize("mode", [InputMode.AGENT_SOLO, InputMode.COWORK])
    def test_true_for_active_modes(self, gate: InputGate, input_status, mode) -> None:
        gate.set_mode(mode)
        result = _run(input_status())
        assert result["agent_can_input"] is True

    @pytest.mark.parametrize(
        "mode",
        [InputMode.HUMAN_OVERRIDE, InputMode.HUMAN_HOME, InputMode.EMERGENCY_STOP],
    )
    def test_false_for_blocking_modes(self, gate: InputGate, input_status, mode) -> None:
        gate.set_mode(mode)
        result = _run(input_status())
        assert result["agent_can_input"] is False


# ---------------------------------------------------------------------------
# Description matches mode
# ---------------------------------------------------------------------------


class TestDescriptionMatchesMode:
    @pytest.mark.parametrize("mode", list(InputMode))
    def test_description_for_each_mode(self, gate: InputGate, input_status, mode) -> None:
        if mode is InputMode.EMERGENCY_STOP:
            gate.set_mode(mode)
        elif mode is InputMode.HUMAN_HOME:
            pass  # already default
        else:
            gate.set_mode(mode)
        result = _run(input_status())
        assert result["description"] == _mode_descriptions[mode]
