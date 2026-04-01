# InputDecayMonitor — `desktop/monitor.py`

Detects human idle gaps using a single exponential decay variable. The core scheduling signal for COWORK mode.

## The Math

One state variable: `activity` (float).

```
On each human input event:
    activity += 1.0

Continuously:
    activity *= e^(-λΔt)    where λ = ln(2) / half_life_ms

Agent can fire when:
    activity < threshold
```

```
Human input:  ↓ ↓↓ ↓↓↓  ↓ ↓              ↓↓  ↓
activity:    ─╱╲╱╲╱╲╱╲──╱╲╱╲──────────────╱╲──╱╲─
threshold ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─╲─ ─ ─ ─ ─ ─ ─ ─
                                  ╲________╱
                                   AGENT
                                   FIRES
```

No history buffer. No sliding window. The decay **is** the prediction.

## Public API

```python
class InputDecayMonitor:
    DEFAULT_HALF_LIFE_MS = 150.0   # 150ms = detects brief typing pauses
    DEFAULT_THRESHOLD = 0.1

    def on_input(self) -> None         # Call on every human input event
    def agent_can_fire(self) -> bool   # True = gap detected
    def current_activity(self) -> float # For diagnostics

    def update_parameters(self, half_life_ms=None, threshold=None) -> None
        # ML hook — swap internals, keep interface
        # A future model tunes these two values adaptively

    @property half_life_ms -> float
    @property threshold -> float
```

## Parameters

| Parameter | Default | Effect |
|-----------|---------|--------|
| `half_life_ms` | 150 | How fast activity decays. Lower = more aggressive gap detection |
| `threshold` | 0.1 | Below this, agent fires. Lower = waits for deeper idle |

## Decay Implementation

`_decay()` is called at the start of both `on_input()` and `agent_can_fire()`. It computes elapsed time since last call and multiplies activity by the decay factor. Uses `time.perf_counter_ns()` for precision.

## Thread Safety

`threading.Lock` protects `_activity` and `_last_update_ns`. Both `on_input()` (from raw input thread) and `agent_can_fire()` (from scheduler thread) acquire the lock.
