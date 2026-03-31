"""Tests for InputDecayMonitor — exponential decay gap detection."""

from __future__ import annotations

import math
import threading
from unittest.mock import patch

import pytest

from windowspc_mcp.desktop.monitor import InputDecayMonitor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NS_PER_MS = 1_000_000


def _make_monitor_with_clock(
    half_life_ms: float = InputDecayMonitor.DEFAULT_HALF_LIFE_MS,
    threshold: float = InputDecayMonitor.DEFAULT_THRESHOLD,
):
    """Create a monitor with a controllable clock.

    Returns (monitor, advance_ms) where advance_ms(dt) moves the clock
    forward by *dt* milliseconds.
    """
    current_ns = [0]

    def fake_perf_counter_ns() -> int:
        return current_ns[0]

    def advance_ms(dt: float) -> None:
        current_ns[0] += int(dt * _NS_PER_MS)

    with patch("windowspc_mcp.desktop.monitor.time.perf_counter_ns", side_effect=fake_perf_counter_ns):
        monitor = InputDecayMonitor(half_life_ms=half_life_ms, threshold=threshold)

    # Patch the module-level time.perf_counter_ns persistently for this monitor
    monitor._perf_counter_ns = fake_perf_counter_ns
    monitor._advance_ms = advance_ms  # stash for test access
    return monitor, advance_ms, fake_perf_counter_ns


def _call_with_clock(monitor, fake_clock, method_name, *args):
    """Call a monitor method while the clock is patched."""
    with patch("windowspc_mcp.desktop.monitor.time.perf_counter_ns", side_effect=fake_clock):
        return getattr(monitor, method_name)(*args)


# ---------------------------------------------------------------------------
# Tests: initial state
# ---------------------------------------------------------------------------


class TestInitialState:
    def test_initial_activity_is_zero(self):
        mon, _, clock = _make_monitor_with_clock()
        activity = _call_with_clock(mon, clock, "current_activity")
        assert activity == pytest.approx(0.0, abs=1e-12)

    def test_initial_agent_can_fire_is_true(self):
        mon, _, clock = _make_monitor_with_clock()
        assert _call_with_clock(mon, clock, "agent_can_fire") is True


# ---------------------------------------------------------------------------
# Tests: on_input bumps activity
# ---------------------------------------------------------------------------


class TestOnInput:
    def test_single_input_raises_activity(self):
        mon, _, clock = _make_monitor_with_clock()
        _call_with_clock(mon, clock, "on_input")
        activity = _call_with_clock(mon, clock, "current_activity")
        assert activity == pytest.approx(1.0, abs=1e-9)

    def test_single_input_makes_agent_cannot_fire(self):
        """With default threshold=0.1, activity=1.0 should block firing."""
        mon, _, clock = _make_monitor_with_clock()
        _call_with_clock(mon, clock, "on_input")
        assert _call_with_clock(mon, clock, "agent_can_fire") is False

    def test_multiple_rapid_inputs_accumulate(self):
        mon, _, clock = _make_monitor_with_clock()
        for _ in range(5):
            _call_with_clock(mon, clock, "on_input")
        activity = _call_with_clock(mon, clock, "current_activity")
        assert activity == pytest.approx(5.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Tests: decay over time
# ---------------------------------------------------------------------------


class TestDecay:
    def test_half_life_halves_activity(self):
        """After exactly one half-life, activity should be ~0.5 of peak."""
        half_life = 150.0
        mon, advance, clock = _make_monitor_with_clock(half_life_ms=half_life)
        _call_with_clock(mon, clock, "on_input")  # activity = 1.0
        advance(half_life)
        activity = _call_with_clock(mon, clock, "current_activity")
        assert activity == pytest.approx(0.5, rel=1e-6)

    def test_two_half_lives_quarters_activity(self):
        half_life = 150.0
        mon, advance, clock = _make_monitor_with_clock(half_life_ms=half_life)
        _call_with_clock(mon, clock, "on_input")
        advance(2 * half_life)
        activity = _call_with_clock(mon, clock, "current_activity")
        assert activity == pytest.approx(0.25, rel=1e-6)

    def test_decay_below_threshold_enables_firing(self):
        """After enough time, activity decays below threshold and agent can fire."""
        half_life = 150.0
        threshold = 0.1
        mon, advance, clock = _make_monitor_with_clock(
            half_life_ms=half_life, threshold=threshold,
        )
        _call_with_clock(mon, clock, "on_input")  # activity = 1.0
        # Need activity < 0.1, so 1.0 * 2^(-n) < 0.1 => n > log2(10) ≈ 3.32
        # Use 4 half-lives => activity ≈ 0.0625
        advance(4 * half_life)
        assert _call_with_clock(mon, clock, "agent_can_fire") is True

    def test_decay_is_continuous_not_stepped(self):
        """Verify decay works for fractional half-life intervals."""
        half_life = 200.0
        mon, advance, clock = _make_monitor_with_clock(half_life_ms=half_life)
        _call_with_clock(mon, clock, "on_input")  # activity = 1.0
        advance(100.0)  # half a half-life
        activity = _call_with_clock(mon, clock, "current_activity")
        expected = math.exp(-math.log(2) / 200.0 * 100.0)
        assert activity == pytest.approx(expected, rel=1e-6)

    def test_zero_elapsed_time_no_decay(self):
        """When no time passes, no decay occurs."""
        mon, _, clock = _make_monitor_with_clock()
        _call_with_clock(mon, clock, "on_input")
        # Read immediately — zero dt
        activity = _call_with_clock(mon, clock, "current_activity")
        assert activity == pytest.approx(1.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Tests: threshold boundary
# ---------------------------------------------------------------------------


class TestThresholdBoundary:
    def test_activity_exactly_at_threshold_cannot_fire(self):
        """agent_can_fire requires activity *strictly below* threshold."""
        # Set threshold = 1.0 and inject exactly 1.0 of activity
        mon, _, clock = _make_monitor_with_clock(threshold=1.0)
        _call_with_clock(mon, clock, "on_input")  # activity = 1.0
        assert _call_with_clock(mon, clock, "agent_can_fire") is False

    def test_activity_just_below_threshold_can_fire(self):
        mon, advance, clock = _make_monitor_with_clock(
            half_life_ms=100.0, threshold=0.5,
        )
        _call_with_clock(mon, clock, "on_input")  # activity = 1.0
        # After 1 half-life: activity = 0.5 (exactly at threshold, not below)
        # Go slightly past
        advance(101.0)
        assert _call_with_clock(mon, clock, "agent_can_fire") is True


# ---------------------------------------------------------------------------
# Tests: update_parameters
# ---------------------------------------------------------------------------


class TestUpdateParameters:
    def test_update_half_life(self):
        mon, _, clock = _make_monitor_with_clock(half_life_ms=150.0)
        _call_with_clock(mon, clock, "update_parameters", 300.0, None)
        assert mon.half_life_ms == pytest.approx(300.0, rel=1e-9)

    def test_update_threshold(self):
        mon, _, clock = _make_monitor_with_clock(threshold=0.1)
        _call_with_clock(mon, clock, "update_parameters", None, 0.5)
        assert mon.threshold == pytest.approx(0.5)

    def test_update_both(self):
        mon, _, clock = _make_monitor_with_clock()
        _call_with_clock(mon, clock, "update_parameters", 400.0, 0.3)
        assert mon.half_life_ms == pytest.approx(400.0, rel=1e-9)
        assert mon.threshold == pytest.approx(0.3)

    def test_updated_threshold_affects_agent_can_fire(self):
        """Raising threshold above current activity should enable firing."""
        mon, _, clock = _make_monitor_with_clock(threshold=0.1)
        _call_with_clock(mon, clock, "on_input")  # activity = 1.0
        assert _call_with_clock(mon, clock, "agent_can_fire") is False
        _call_with_clock(mon, clock, "update_parameters", None, 2.0)
        assert _call_with_clock(mon, clock, "agent_can_fire") is True

    def test_updated_half_life_affects_decay_rate(self):
        """Shorter half-life means faster decay."""
        mon, advance, clock = _make_monitor_with_clock(half_life_ms=1000.0)
        _call_with_clock(mon, clock, "on_input")
        # Change to very short half-life
        _call_with_clock(mon, clock, "update_parameters", 10.0, None)
        advance(100.0)  # 10 half-lives at 10ms each
        activity = _call_with_clock(mon, clock, "current_activity")
        # 1.0 * 2^(-10) ≈ 0.000977
        assert activity == pytest.approx(1.0 / 1024.0, rel=1e-3)


# ---------------------------------------------------------------------------
# Tests: properties
# ---------------------------------------------------------------------------


class TestProperties:
    def test_half_life_ms_property(self):
        mon, _, _ = _make_monitor_with_clock(half_life_ms=250.0)
        assert mon.half_life_ms == pytest.approx(250.0, rel=1e-9)

    def test_threshold_property(self):
        mon, _, _ = _make_monitor_with_clock(threshold=0.42)
        assert mon.threshold == pytest.approx(0.42)

    def test_default_half_life(self):
        assert InputDecayMonitor.DEFAULT_HALF_LIFE_MS == 150.0

    def test_default_threshold(self):
        assert InputDecayMonitor.DEFAULT_THRESHOLD == 0.1


# ---------------------------------------------------------------------------
# Tests: thread safety
# ---------------------------------------------------------------------------


class TestThreadSafety:
    def test_concurrent_on_input_and_agent_can_fire(self):
        """Hammer on_input and agent_can_fire from multiple threads.

        We don't assert specific activity values — just that it doesn't crash,
        deadlock, or raise exceptions.
        """
        mon = InputDecayMonitor()
        errors: list[Exception] = []
        stop = threading.Event()

        def input_worker():
            try:
                for _ in range(500):
                    if stop.is_set():
                        break
                    mon.on_input()
            except Exception as exc:
                errors.append(exc)
                stop.set()

        def reader_worker():
            try:
                for _ in range(500):
                    if stop.is_set():
                        break
                    mon.agent_can_fire()
                    mon.current_activity()
            except Exception as exc:
                errors.append(exc)
                stop.set()

        threads = [
            threading.Thread(target=input_worker),
            threading.Thread(target=input_worker),
            threading.Thread(target=reader_worker),
            threading.Thread(target=reader_worker),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Thread errors: {errors}"
        # All threads should have finished
        for t in threads:
            assert not t.is_alive(), "Thread did not finish in time"

    def test_concurrent_update_parameters(self):
        """Concurrent parameter updates shouldn't corrupt state."""
        mon = InputDecayMonitor()
        errors: list[Exception] = []

        def updater(half_life: float, threshold: float):
            try:
                for _ in range(200):
                    mon.update_parameters(half_life_ms=half_life, threshold=threshold)
                    mon.on_input()
                    mon.agent_can_fire()
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=updater, args=(100.0, 0.1)),
            threading.Thread(target=updater, args=(300.0, 0.5)),
            threading.Thread(target=updater, args=(50.0, 0.01)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Thread errors: {errors}"


# ---------------------------------------------------------------------------
# Tests: edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_many_inputs_then_long_decay(self):
        """Even many accumulated inputs decay to zero eventually."""
        mon, advance, clock = _make_monitor_with_clock(half_life_ms=100.0, threshold=0.1)
        for _ in range(100):
            _call_with_clock(mon, clock, "on_input")
        # activity = 100.0. Need 100 * 2^(-n) < 0.1 => n > log2(1000) ≈ 9.97
        # 10 half-lives = 1000ms
        advance(1000.0)
        assert _call_with_clock(mon, clock, "agent_can_fire") is True
        activity = _call_with_clock(mon, clock, "current_activity")
        assert activity < 0.1

    def test_input_during_decay(self):
        """Input event in the middle of decay correctly adds to decayed value."""
        half_life = 100.0
        mon, advance, clock = _make_monitor_with_clock(half_life_ms=half_life)
        _call_with_clock(mon, clock, "on_input")  # activity = 1.0
        advance(half_life)  # activity decays to 0.5
        _call_with_clock(mon, clock, "on_input")  # activity = 0.5 + 1.0 = 1.5
        activity = _call_with_clock(mon, clock, "current_activity")
        assert activity == pytest.approx(1.5, rel=1e-6)
