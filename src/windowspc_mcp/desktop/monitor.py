"""Exponential-decay human idle-gap detector for COWORK mode.

One floating-point variable ``activity`` tracks human input intensity.

* On every human input event: ``activity += 1.0``
* Continuously: ``activity`` decays by ``e^{-λΔt}`` where ``λ = ln(2) / half_life``
* Agent can fire when: ``activity < threshold``
"""

from __future__ import annotations

import math
import threading
import time


class InputDecayMonitor:
    """Detects human idle gaps using exponential decay.

    One variable. Two parameters. No history buffer.
    """

    DEFAULT_HALF_LIFE_MS: float = 150.0  # How fast activity decays
    DEFAULT_THRESHOLD: float = 0.1  # Below this = gap detected

    def __init__(
        self,
        half_life_ms: float = DEFAULT_HALF_LIFE_MS,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> None:
        """Initialize with configurable decay rate and threshold.

        Args:
            half_life_ms: Time in ms for activity to halve.
                         150ms = detects brief typing pauses.
                         300ms = waits for real idle moments.
            threshold: Activity level below which agent_can_fire() returns True.
        """
        if half_life_ms <= 0:
            raise ValueError(f"half_life_ms must be positive, got {half_life_ms}")
        self._lambda = math.log(2) / half_life_ms
        self._threshold = threshold
        self._activity = 0.0
        self._last_update_ns: int = time.perf_counter_ns()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def on_input(self) -> None:
        """Call on every human input event (key press, mouse move, click).

        Thread-safe.
        """
        with self._lock:
            self._decay()
            self._activity += 1.0

    def agent_can_fire(self) -> bool:
        """Is the human in a gap? Thread-safe."""
        with self._lock:
            self._decay()
            return self._activity < self._threshold

    def current_activity(self) -> float:
        """Current activity level (for diagnostics / InputStatus). Thread-safe."""
        with self._lock:
            self._decay()
            return self._activity

    @property
    def half_life_ms(self) -> float:
        """Current half-life setting."""
        return math.log(2) / self._lambda

    @property
    def threshold(self) -> float:
        """Current threshold setting."""
        return self._threshold

    def update_parameters(
        self,
        half_life_ms: float | None = None,
        threshold: float | None = None,
    ) -> None:
        """Update decay parameters at runtime. Thread-safe.

        This is the ML hook — a future model adjusts these two values.
        """
        with self._lock:
            if half_life_ms is not None:
                if half_life_ms <= 0:
                    raise ValueError(f"half_life_ms must be positive, got {half_life_ms}")
                self._lambda = math.log(2) / half_life_ms
            if threshold is not None:
                self._threshold = threshold

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _decay(self) -> None:
        """Apply exponential decay since last update. Must be called with lock held."""
        now = time.perf_counter_ns()
        dt_ms = (now - self._last_update_ns) / 1_000_000
        self._last_update_ns = now
        self._activity *= math.exp(-self._lambda * dt_ms)
