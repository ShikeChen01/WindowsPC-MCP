# InputGate — `desktop/gate.py`

The single checkpoint that every agent input operation passes through. Checks the current mode and either allows, queues, or rejects the operation.

## Modes

```python
class InputMode(Enum):
    AGENT_SOLO      # Pass — direct SendInput, no scheduling
    COWORK          # Pass — caller handles scheduling via CursorScheduler
    HUMAN_OVERRIDE  # Block — raises AgentPreempted
    HUMAN_HOME      # Block — raises AgentPaused
    EMERGENCY_STOP  # Block — raises EmergencyStop (terminal)
```

## Public API

```python
class InputGate:
    def __init__(self)
        # Default mode: HUMAN_HOME (safe default)

    @property
    def mode(self) -> InputMode
        # Lockless read — safe because Python GIL guarantees atomic
        # reference reads, and InputMode members are immutable singletons

    def set_mode(self, mode: InputMode) -> None
        # Thread-safe transition
        # EMERGENCY_STOP is terminal — cannot leave it
        # Re-setting same mode is a no-op
        # Notifies listeners with (old_mode, new_mode)

    def check(self) -> None
        # Called before EVERY agent input operation
        # Must be fast — single attribute read + conditional raise
        # AGENT_SOLO / COWORK → returns (pass)
        # HUMAN_OVERRIDE → raises AgentPreempted
        # HUMAN_HOME → raises AgentPaused
        # EMERGENCY_STOP → raises EmergencyStop

    def on_mode_change(self, callback: Callable[[InputMode, InputMode], None]) -> None
    def remove_listener(self, callback) -> None
```

## Listener Contract

- Listeners fire synchronously in the thread that calls `set_mode()`
- Listeners are called **outside the lock** — prevents deadlocks if listener calls back into gate
- Listener list is snapshotted under lock, then iterated outside lock
- Listener exceptions are caught and logged — never prevent mode transition

## Terminal State

`EMERGENCY_STOP` is a one-way door. `set_mode()` to any other mode raises `InvalidStateError`. Re-setting `EMERGENCY_STOP` is a silent no-op.
