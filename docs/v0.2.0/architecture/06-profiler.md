# ActionProfiler — `desktop/profiler.py`

Estimates how long agent input actions take. Used by CursorScheduler to decide if an action fits in a detected gap.

## Action Types

```python
class ActionType(Enum):
    MOVE          # SetCursorPos
    CLICK         # move + mousedown + mouseup
    DOUBLE_CLICK  # move + 2x(down+up)
    KEY           # single keystroke
    STRING        # multi-character typing
    SCROLL        # single wheel event
    DRAG          # down + move + up
```

## Lifecycle

```text
Startup:    calibrate() or set_default_timings()
                    │
                    ▼
Runtime:    estimate(action_type, complexity) → ms
                    │
            (agent executes action)
                    │
                    ▼
            record(action_type, actual_ms) → EMA update
```

## Public API

```python
class ActionProfiler:
    EMA_ALPHA = 0.2  # Weight for runtime updates

    def calibrate(self, benchmark_fn: dict[ActionType, Callable]) -> None
        # Runs each function 20 times, records mean and p95

    def set_default_timings(self) -> None
        # Hardcoded fallbacks (e.g., CLICK=1.0ms p95, MOVE=0.1ms p95)

    def estimate(self, action_type, complexity=1.0) -> float
        # Returns p95 * complexity (conservative)
        # complexity: 1.0 for click, len(text)/4 for string, etc.

    def record(self, action_type, actual_ms) -> None
        # EMA update: mean = 0.8*mean + 0.2*actual
        # p95 = 0.8*p95 + 0.2*max(p95, actual)
        # Creates new entry for unknown types

    def get_timing(self, action_type) -> ActionTiming | None
    @property is_calibrated -> bool
```

## EMA (Exponential Moving Average)

After every real execution, `record()` adjusts the stored timings:
- **Mean** shifts toward actual: `mean = 0.8 * mean + 0.2 * actual`
- **P95** only increases aggressively (tracks worst case): `p95 = 0.8 * p95 + 0.2 * max(p95, actual)`

This means the profiler self-corrects over time without needing to store history.

## Thread Safety

No locking. The profiler is only accessed by the CursorScheduler's dispatch thread (single consumer). `calibrate()` runs before the scheduler starts.
