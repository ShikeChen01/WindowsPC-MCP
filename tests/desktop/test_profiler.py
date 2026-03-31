"""Tests for ActionProfiler — startup calibration + runtime EMA."""

from __future__ import annotations

import pytest

from windowspc_mcp.desktop.profiler import ActionProfiler, ActionTiming, ActionType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def profiler() -> ActionProfiler:
    """Fresh ActionProfiler with no timings."""
    return ActionProfiler()


@pytest.fixture
def profiler_with_defaults() -> ActionProfiler:
    """ActionProfiler with default timings loaded."""
    p = ActionProfiler()
    p.set_default_timings()
    return p


# ---------------------------------------------------------------------------
# set_default_timings
# ---------------------------------------------------------------------------

class TestSetDefaultTimings:
    def test_provides_all_action_types(self, profiler: ActionProfiler) -> None:
        profiler.set_default_timings()
        for action_type in ActionType:
            timing = profiler.get_timing(action_type)
            assert timing is not None, f"Missing default timing for {action_type}"

    def test_defaults_have_zero_samples(self, profiler: ActionProfiler) -> None:
        profiler.set_default_timings()
        for action_type in ActionType:
            timing = profiler.get_timing(action_type)
            assert timing is not None
            assert timing.samples == 0

    def test_p95_greater_or_equal_to_mean(self, profiler: ActionProfiler) -> None:
        profiler.set_default_timings()
        for action_type in ActionType:
            timing = profiler.get_timing(action_type)
            assert timing is not None
            assert timing.p95 >= timing.mean


# ---------------------------------------------------------------------------
# calibrate
# ---------------------------------------------------------------------------

class TestCalibrate:
    def test_records_correct_timings(self, profiler: ActionProfiler) -> None:
        """Calibrate with a mock function and verify timing is recorded."""
        call_count = 0

        def mock_move() -> None:
            nonlocal call_count
            call_count += 1

        profiler.calibrate({ActionType.MOVE: mock_move})

        assert call_count == 20
        timing = profiler.get_timing(ActionType.MOVE)
        assert timing is not None
        assert timing.samples == 20
        assert timing.mean >= 0
        assert timing.p95 >= 0

    def test_calibrate_multiple_action_types(self, profiler: ActionProfiler) -> None:
        """Calibrate several action types at once."""
        fns = {
            ActionType.MOVE: lambda: None,
            ActionType.CLICK: lambda: None,
            ActionType.KEY: lambda: None,
        }
        profiler.calibrate(fns)

        for at in fns:
            timing = profiler.get_timing(at)
            assert timing is not None
            assert timing.samples == 20

    def test_calibrate_sets_is_calibrated(self, profiler: ActionProfiler) -> None:
        assert not profiler.is_calibrated
        profiler.calibrate({ActionType.MOVE: lambda: None})
        assert profiler.is_calibrated


# ---------------------------------------------------------------------------
# estimate
# ---------------------------------------------------------------------------

class TestEstimate:
    def test_uses_p95(self, profiler_with_defaults: ActionProfiler) -> None:
        """Estimate with complexity=1.0 should return the p95 value."""
        timing = profiler_with_defaults.get_timing(ActionType.CLICK)
        assert timing is not None
        est = profiler_with_defaults.estimate(ActionType.CLICK)
        assert est == pytest.approx(timing.p95)

    def test_complexity_scales_estimate(self, profiler_with_defaults: ActionProfiler) -> None:
        """Complexity multiplier should scale the estimate."""
        base = profiler_with_defaults.estimate(ActionType.STRING, complexity=1.0)
        scaled = profiler_with_defaults.estimate(ActionType.STRING, complexity=3.0)
        assert scaled == pytest.approx(base * 3.0)

    def test_various_complexity_values(self, profiler_with_defaults: ActionProfiler) -> None:
        """Verify scaling at several complexity levels."""
        for factor in [0.5, 1.0, 2.0, 4.0, 10.0]:
            est = profiler_with_defaults.estimate(ActionType.DRAG, complexity=factor)
            timing = profiler_with_defaults.get_timing(ActionType.DRAG)
            assert timing is not None
            assert est == pytest.approx(timing.p95 * factor)

    def test_raises_key_error_for_unknown(self, profiler: ActionProfiler) -> None:
        """Estimate on uncalibrated profiler should raise KeyError."""
        with pytest.raises(KeyError):
            profiler.estimate(ActionType.MOVE)


# ---------------------------------------------------------------------------
# record (EMA updates)
# ---------------------------------------------------------------------------

class TestRecord:
    def test_creates_new_entry_for_unknown(self, profiler: ActionProfiler) -> None:
        """Recording an unknown action type should create a new entry."""
        profiler.record(ActionType.SCROLL, 1.5)
        timing = profiler.get_timing(ActionType.SCROLL)
        assert timing is not None
        assert timing.mean == pytest.approx(1.5)
        assert timing.p95 == pytest.approx(1.5)
        assert timing.samples == 1

    def test_ema_shifts_mean_toward_new_value(
        self, profiler_with_defaults: ActionProfiler
    ) -> None:
        """After recording, mean should shift toward the recorded value."""
        old = profiler_with_defaults.get_timing(ActionType.CLICK)
        assert old is not None
        old_mean = old.mean

        # Record a value much higher than the default mean (0.5)
        profiler_with_defaults.record(ActionType.CLICK, 10.0)

        new = profiler_with_defaults.get_timing(ActionType.CLICK)
        assert new is not None
        assert new.mean > old_mean

    def test_ema_shifts_p95_toward_new_value_when_higher(
        self, profiler_with_defaults: ActionProfiler
    ) -> None:
        """When actual > p95, p95 should increase."""
        old = profiler_with_defaults.get_timing(ActionType.CLICK)
        assert old is not None
        old_p95 = old.p95

        # Record a value much higher than the default p95 (1.0)
        profiler_with_defaults.record(ActionType.CLICK, 50.0)

        new = profiler_with_defaults.get_timing(ActionType.CLICK)
        assert new is not None
        assert new.p95 > old_p95

    def test_p95_does_not_decrease_on_low_value(
        self, profiler_with_defaults: ActionProfiler
    ) -> None:
        """When actual < p95, p95 should remain unchanged (EMA uses max(p95, actual))."""
        old = profiler_with_defaults.get_timing(ActionType.CLICK)
        assert old is not None
        old_p95 = old.p95

        # Record a value much lower than p95
        profiler_with_defaults.record(ActionType.CLICK, 0.001)

        new = profiler_with_defaults.get_timing(ActionType.CLICK)
        assert new is not None
        # p95 EMA with max(p95, actual) where actual < p95 => max = p95
        # so p95 = 0.8 * 1.0 + 0.2 * 1.0 = 1.0 (unchanged)
        assert new.p95 == pytest.approx(old_p95)

    def test_record_increments_samples(
        self, profiler_with_defaults: ActionProfiler
    ) -> None:
        """Each record call should increment the sample count."""
        old = profiler_with_defaults.get_timing(ActionType.KEY)
        assert old is not None
        old_samples = old.samples

        profiler_with_defaults.record(ActionType.KEY, 0.2)
        profiler_with_defaults.record(ActionType.KEY, 0.3)

        new = profiler_with_defaults.get_timing(ActionType.KEY)
        assert new is not None
        assert new.samples == old_samples + 2

    def test_ema_formula_correctness(self, profiler: ActionProfiler) -> None:
        """Verify the exact EMA math for mean."""
        alpha = ActionProfiler.EMA_ALPHA
        profiler.record(ActionType.MOVE, 1.0)  # creates entry: mean=1.0
        profiler.record(ActionType.MOVE, 5.0)  # EMA update

        timing = profiler.get_timing(ActionType.MOVE)
        assert timing is not None
        expected_mean = (1 - alpha) * 1.0 + alpha * 5.0
        assert timing.mean == pytest.approx(expected_mean)

    def test_multiple_records_converge(self, profiler_with_defaults: ActionProfiler) -> None:
        """After many records of the same value, mean should converge toward it."""
        target = 10.0
        for _ in range(100):
            profiler_with_defaults.record(ActionType.MOVE, target)

        timing = profiler_with_defaults.get_timing(ActionType.MOVE)
        assert timing is not None
        # After 100 EMA updates with alpha=0.2, mean converges very close to target
        assert timing.mean == pytest.approx(target, rel=0.01)


# ---------------------------------------------------------------------------
# is_calibrated
# ---------------------------------------------------------------------------

class TestIsCalibrated:
    def test_starts_false(self, profiler: ActionProfiler) -> None:
        assert not profiler.is_calibrated

    def test_true_after_defaults(self, profiler: ActionProfiler) -> None:
        profiler.set_default_timings()
        assert profiler.is_calibrated

    def test_true_after_calibration(self, profiler: ActionProfiler) -> None:
        profiler.calibrate({ActionType.MOVE: lambda: None})
        assert profiler.is_calibrated

    def test_true_after_record(self, profiler: ActionProfiler) -> None:
        profiler.record(ActionType.CLICK, 0.5)
        assert profiler.is_calibrated


# ---------------------------------------------------------------------------
# get_timing
# ---------------------------------------------------------------------------

class TestGetTiming:
    def test_returns_none_for_unknown(self, profiler: ActionProfiler) -> None:
        assert profiler.get_timing(ActionType.MOVE) is None

    def test_returns_correct_data(self, profiler_with_defaults: ActionProfiler) -> None:
        timing = profiler_with_defaults.get_timing(ActionType.MOVE)
        assert timing is not None
        assert isinstance(timing, ActionTiming)
        assert timing.mean == pytest.approx(0.05)
        assert timing.p95 == pytest.approx(0.1)
        assert timing.samples == 0
