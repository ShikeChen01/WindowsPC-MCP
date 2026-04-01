# DesktopController — `desktop/controller.py`

The integration layer that wires DesktopManager, HotkeyService, and InputGate together. Owns mode transition logic.

## Public API

```python
class DesktopController:
    def __init__(self, desktop_manager, input_gate, hotkey_service)

    def start(self, initial_mode=InputMode.AGENT_SOLO) -> None
        # 1. Create agent desktop
        # 2. Wire hotkey callbacks: TOGGLE→toggle_mode, OVERRIDE→override, EMERGENCY→emergency_stop
        # 3. Start hotkey service
        # 4. Set initial mode on input gate
        # 5. Switch to agent desktop if initial mode requires it

    def stop(self) -> None
        # 1. Stop hotkey service
        # 2. Switch to user desktop
        # 3. Destroy agent desktop

    def toggle_mode(self) -> None
    def override(self) -> None
    def resume_from_override(self) -> None
    def emergency_stop(self) -> None

    # Context manager: __enter__→start(), __exit__→stop()
```

## Toggle Cycle

```text
AGENT_SOLO ──► COWORK ──► HUMAN_HOME ──► AGENT_SOLO
                                              │
                                         (loops back)
```

- HUMAN_OVERRIDE → ignored (must `resume_from_override()` first)
- EMERGENCY_STOP → ignored

## Override Mechanism

```text
override():
    save current mode → _pre_override_mode
    set HUMAN_OVERRIDE
    if was on agent desktop → switch to user

resume_from_override():
    restore _pre_override_mode
    if restored mode needs agent desktop → switch back
    only valid when current mode IS HUMAN_OVERRIDE
```

## Emergency Stop

```text
emergency_stop():
    set EMERGENCY_STOP on gate (terminal)
    switch to user desktop
    destroy agent desktop (kills all agent processes)
    stop hotkey service
```

Idempotent — safe to call multiple times.

## Desktop Switching

The controller tracks which modes need the agent desktop:
- `AGENT_SOLO`, `COWORK` → agent desktop is input desktop
- `HUMAN_HOME`, `HUMAN_OVERRIDE` → user desktop is input desktop

On every mode transition, the controller calls `switch_to_agent()` or `switch_to_user()` accordingly.

## Thread Safety

`threading.Lock` serializes all transition methods. Hotkey callbacks come from the listener thread — the lock prevents concurrent hotkey presses from corrupting state.
