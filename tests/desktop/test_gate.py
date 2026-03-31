"""Tests for InputGate — mode-based routing for agent input."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from windowspc_mcp.confinement.errors import (
    AgentPaused,
    AgentPreempted,
    EmergencyStop,
    InvalidStateError,
)
from windowspc_mcp.desktop.gate import InputGate, InputMode


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def gate() -> InputGate:
    return InputGate()


# ---------------------------------------------------------------------------
# Default state
# ---------------------------------------------------------------------------


class TestDefaultState:
    def test_default_mode_is_human_home(self, gate: InputGate) -> None:
        assert gate.mode is InputMode.HUMAN_HOME

    def test_check_raises_agent_paused_by_default(self, gate: InputGate) -> None:
        with pytest.raises(AgentPaused):
            gate.check()


# ---------------------------------------------------------------------------
# check() behaviour per mode
# ---------------------------------------------------------------------------


class TestCheckPassThrough:
    """Modes where check() should return without raising."""

    def test_agent_solo(self, gate: InputGate) -> None:
        gate.set_mode(InputMode.AGENT_SOLO)
        gate.check()  # should not raise

    def test_cowork(self, gate: InputGate) -> None:
        gate.set_mode(InputMode.COWORK)
        gate.check()  # should not raise


class TestCheckBlocking:
    """Modes where check() should raise."""

    def test_human_override_raises_agent_preempted(self, gate: InputGate) -> None:
        gate.set_mode(InputMode.HUMAN_OVERRIDE)
        with pytest.raises(AgentPreempted):
            gate.check()

    def test_human_home_raises_agent_paused(self, gate: InputGate) -> None:
        # Already the default, but explicit for clarity.
        assert gate.mode is InputMode.HUMAN_HOME
        with pytest.raises(AgentPaused):
            gate.check()

    def test_emergency_stop_raises_emergency_stop(self, gate: InputGate) -> None:
        gate.set_mode(InputMode.EMERGENCY_STOP)
        with pytest.raises(EmergencyStop):
            gate.check()


# ---------------------------------------------------------------------------
# Mode transitions
# ---------------------------------------------------------------------------


class TestSetMode:
    def test_transition_updates_mode(self, gate: InputGate) -> None:
        gate.set_mode(InputMode.AGENT_SOLO)
        assert gate.mode is InputMode.AGENT_SOLO

    def test_same_mode_is_noop(self, gate: InputGate) -> None:
        """Setting the same mode doesn't fire listeners."""
        calls: list[tuple[InputMode, InputMode]] = []
        gate.on_mode_change(lambda old, new: calls.append((old, new)))
        gate.set_mode(InputMode.HUMAN_HOME)  # already HUMAN_HOME
        assert calls == []

    def test_round_trip(self, gate: InputGate) -> None:
        gate.set_mode(InputMode.AGENT_SOLO)
        gate.set_mode(InputMode.COWORK)
        gate.set_mode(InputMode.HUMAN_OVERRIDE)
        gate.set_mode(InputMode.HUMAN_HOME)
        assert gate.mode is InputMode.HUMAN_HOME


# ---------------------------------------------------------------------------
# EMERGENCY_STOP is terminal
# ---------------------------------------------------------------------------


class TestEmergencyStopTerminal:
    def test_cannot_transition_out(self, gate: InputGate) -> None:
        gate.set_mode(InputMode.EMERGENCY_STOP)
        with pytest.raises(InvalidStateError, match="EMERGENCY_STOP"):
            gate.set_mode(InputMode.AGENT_SOLO)

    def test_cannot_transition_to_human_home(self, gate: InputGate) -> None:
        gate.set_mode(InputMode.EMERGENCY_STOP)
        with pytest.raises(InvalidStateError):
            gate.set_mode(InputMode.HUMAN_HOME)

    def test_set_emergency_stop_again_is_noop(self, gate: InputGate) -> None:
        """Re-setting EMERGENCY_STOP when already stopped is a no-op."""
        gate.set_mode(InputMode.EMERGENCY_STOP)
        gate.set_mode(InputMode.EMERGENCY_STOP)  # should not raise
        assert gate.mode is InputMode.EMERGENCY_STOP


# ---------------------------------------------------------------------------
# Listeners
# ---------------------------------------------------------------------------


class TestListeners:
    def test_listener_called_with_old_and_new(self, gate: InputGate) -> None:
        calls: list[tuple[InputMode, InputMode]] = []
        gate.on_mode_change(lambda old, new: calls.append((old, new)))

        gate.set_mode(InputMode.AGENT_SOLO)

        assert calls == [(InputMode.HUMAN_HOME, InputMode.AGENT_SOLO)]

    def test_multiple_listeners(self, gate: InputGate) -> None:
        results_a: list[InputMode] = []
        results_b: list[InputMode] = []
        gate.on_mode_change(lambda _old, new: results_a.append(new))
        gate.on_mode_change(lambda _old, new: results_b.append(new))

        gate.set_mode(InputMode.COWORK)

        assert results_a == [InputMode.COWORK]
        assert results_b == [InputMode.COWORK]

    def test_listener_exception_does_not_crash_set_mode(
        self, gate: InputGate
    ) -> None:
        def bad_listener(_old: InputMode, _new: InputMode) -> None:
            raise RuntimeError("boom")

        good_calls: list[InputMode] = []

        gate.on_mode_change(bad_listener)
        gate.on_mode_change(lambda _old, new: good_calls.append(new))

        # Should not raise even though first listener explodes.
        gate.set_mode(InputMode.AGENT_SOLO)
        assert gate.mode is InputMode.AGENT_SOLO
        # Second listener should still have been called.
        assert good_calls == [InputMode.AGENT_SOLO]

    def test_remove_listener(self, gate: InputGate) -> None:
        calls: list[InputMode] = []
        cb = lambda _old, new: calls.append(new)
        gate.on_mode_change(cb)
        gate.set_mode(InputMode.AGENT_SOLO)
        assert len(calls) == 1

        gate.remove_listener(cb)
        gate.set_mode(InputMode.COWORK)
        # Should NOT have received the second transition.
        assert len(calls) == 1

    def test_remove_nonexistent_listener_is_silent(self, gate: InputGate) -> None:
        gate.remove_listener(lambda _o, _n: None)  # should not raise


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


class TestThreadSafety:
    def test_concurrent_set_mode_and_check(self, gate: InputGate) -> None:
        """Hammer set_mode and check from many threads; nothing should corrupt."""
        gate.set_mode(InputMode.AGENT_SOLO)
        errors: list[Exception] = []
        barrier = threading.Barrier(20)

        modes = [
            InputMode.AGENT_SOLO,
            InputMode.COWORK,
            InputMode.HUMAN_OVERRIDE,
            InputMode.HUMAN_HOME,
        ]

        def writer(idx: int) -> None:
            barrier.wait()
            for _ in range(200):
                try:
                    gate.set_mode(modes[idx % len(modes)])
                except InvalidStateError:
                    pass  # fine if we hit EMERGENCY_STOP race
                except Exception as exc:
                    errors.append(exc)

        def reader() -> None:
            barrier.wait()
            for _ in range(200):
                try:
                    gate.check()
                except (AgentPreempted, AgentPaused, EmergencyStop):
                    pass  # expected blocking modes
                except Exception as exc:
                    errors.append(exc)

        with ThreadPoolExecutor(max_workers=20) as pool:
            futures = []
            for i in range(10):
                futures.append(pool.submit(writer, i))
            for _ in range(10):
                futures.append(pool.submit(reader))
            for f in as_completed(futures):
                f.result()

        assert errors == [], f"Unexpected errors: {errors}"

    def test_concurrent_listener_registration(self, gate: InputGate) -> None:
        """Add/remove listeners while set_mode fires; no crashes."""
        gate.set_mode(InputMode.AGENT_SOLO)
        barrier = threading.Barrier(10)

        def registrar() -> None:
            barrier.wait()
            for _ in range(100):
                cb = lambda _o, _n: None
                gate.on_mode_change(cb)
                gate.remove_listener(cb)

        def toggler() -> None:
            barrier.wait()
            for i in range(100):
                try:
                    if i % 2 == 0:
                        gate.set_mode(InputMode.COWORK)
                    else:
                        gate.set_mode(InputMode.AGENT_SOLO)
                except InvalidStateError:
                    pass

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = []
            for _ in range(5):
                futures.append(pool.submit(registrar))
            for _ in range(5):
                futures.append(pool.submit(toggler))
            for f in as_completed(futures):
                f.result()  # will raise if any thread crashed
