"""ActionProfiler — estimates how long agent input actions take.

Calibrated on startup via benchmark functions, then self-corrects at
runtime using an exponential moving average (EMA) of actual measurements.
Used by CursorScheduler to decide whether an action fits in a detected gap.
"""

from __future__ import annotations

import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum


class ActionType(Enum):
    """Types of agent input actions."""

    MOVE = "move"
    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    KEY = "key"  # Single keystroke
    STRING = "string"  # Multi-character typing
    SCROLL = "scroll"
    DRAG = "drag"


@dataclass
class ActionTiming:
    """Timing statistics for an action type."""

    mean: float  # Mean execution time in ms
    p95: float  # 95th percentile in ms
    samples: int  # Number of samples collected


class ActionProfiler:
    """Estimates action execution time. Calibrated on startup, adjusted at runtime."""

    EMA_ALPHA = 0.2  # Exponential moving average weight for runtime updates

    def __init__(self) -> None:
        self._timings: dict[ActionType, ActionTiming] = {}

    def calibrate(self, benchmark_fn: dict[ActionType, Callable[[], None]]) -> None:
        """Run startup calibration. Benchmark each action type 20x.

        Args:
            benchmark_fn: Maps ActionType to a zero-arg function that performs
                         that action once (e.g., SetCursorPos(0,0) for MOVE).
                         The caller provides these because the profiler doesn't
                         know about Win32 APIs directly.
        """
        for action_type, fn in benchmark_fn.items():
            samples: list[float] = []
            for _ in range(20):
                start = time.perf_counter_ns()
                fn()
                elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000
                samples.append(elapsed_ms)

            sorted_samples = sorted(samples)
            self._timings[action_type] = ActionTiming(
                mean=statistics.mean(samples),
                p95=sorted_samples[int(len(sorted_samples) * 0.95)],
                samples=len(samples),
            )

    def set_default_timings(self) -> None:
        """Set reasonable defaults without calibration.

        For environments where benchmark isn't possible (tests, CI).
        """
        defaults: dict[ActionType, tuple[float, float]] = {
            ActionType.MOVE: (0.05, 0.1),  # very fast
            ActionType.CLICK: (0.5, 1.0),  # move + down + up
            ActionType.DOUBLE_CLICK: (1.0, 2.0),  # move + 2x(down+up)
            ActionType.KEY: (0.1, 0.3),  # single key event
            ActionType.STRING: (2.0, 5.0),  # per 4 chars
            ActionType.SCROLL: (0.3, 0.8),  # single wheel event
            ActionType.DRAG: (1.5, 3.0),  # down + move + up
        }
        for action_type, (mean, p95) in defaults.items():
            self._timings[action_type] = ActionTiming(mean=mean, p95=p95, samples=0)

    def estimate(self, action_type: ActionType, complexity: float = 1.0) -> float:
        """Estimate execution time in ms. Uses p95 (conservative).

        Args:
            action_type: The type of action.
            complexity: Multiplier. 1.0 for simple actions.
                       For STRING: len(text) / 4.0
                       For DRAG: distance_factor

        Returns:
            Estimated time in ms.

        Raises:
            KeyError: If action_type has no timing data.
        """
        timing = self._timings[action_type]
        return timing.p95 * complexity

    def record(self, action_type: ActionType, actual_ms: float) -> None:
        """Update timing with actual measurement. Uses EMA.

        Called after every real execution to self-correct.
        """
        if action_type not in self._timings:
            self._timings[action_type] = ActionTiming(
                mean=actual_ms, p95=actual_ms, samples=1
            )
            return

        t = self._timings[action_type]
        t.mean = (1 - self.EMA_ALPHA) * t.mean + self.EMA_ALPHA * actual_ms
        t.p95 = (1 - self.EMA_ALPHA) * t.p95 + self.EMA_ALPHA * max(t.p95, actual_ms)
        t.samples += 1

    def get_timing(self, action_type: ActionType) -> ActionTiming | None:
        """Get timing stats for an action type (for diagnostics)."""
        return self._timings.get(action_type)

    @property
    def is_calibrated(self) -> bool:
        """True if any timings have been loaded."""
        return len(self._timings) > 0
