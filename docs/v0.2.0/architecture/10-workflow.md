# End-to-End Workflow — How Everything Connects

This document traces real scenarios through every module to show how data flows.

---

## Startup

```
Server starts
    │
    ▼
DesktopController.start(initial_mode=AGENT_SOLO)
    │
    ├─1─► DesktopManager.create_agent_desktop()
    │         └── CreateDesktopW("WindowsPC_MCP_Agent")
    │             Result: agent desktop exists in Windows
    │
    ├─2─► HotkeyService.start(callbacks={
    │         TOGGLE:    controller.toggle_mode,
    │         OVERRIDE:  controller.override,
    │         EMERGENCY: controller.emergency_stop,
    │     })
    │         ├── Spawns daemon thread
    │         ├── Creates hidden HWND_MESSAGE window
    │         ├── RegisterHotKey(Ctrl+Alt+Space)
    │         ├── RegisterHotKey(Ctrl+Alt+Enter)
    │         ├── RegisterHotKey(Ctrl+Alt+S)
    │         └── Enters GetMessageW loop (waiting for hotkeys)
    │
    ├─3─► InputGate.set_mode(AGENT_SOLO)
    │         └── Mode is now AGENT_SOLO. Any call to gate.check() passes.
    │
    └─4─► DesktopManager.switch_to_agent()
              └── SwitchDesktop(agent_handle)
                  Result: agent desktop receives all hardware input
```

After startup: agent desktop is live, hotkeys are listening, gate allows all input.

---

## Scenario 1: Agent Clicks in AGENT_SOLO Mode

Simplest case — no scheduling, no contention.

```
LLM calls Click(x=100, y=200)
    │
    ▼
guarded_tool decorator
    │
    ├── ToolGuard.check() — server state is READY, coords valid
    ├── ConfinementEngine.validate_and_translate(100, 200)
    │       └── converts agent-relative → absolute screen coords
    │
    ▼
AgentInputService.click(abs_x, abs_y)
    │
    ├── InputGate.check()
    │       └── mode is AGENT_SOLO → returns immediately (pass)
    │
    ▼
SendInput(mouse_move + mouse_down + mouse_up)
    │
    └── Done. Click happened on agent desktop.
        User is on their own desktop, unaffected.
```

**Modules involved:** guarded_tool → ToolGuard → ConfinementEngine → AgentInputService → InputGate → SendInput

---

## Scenario 2: Agent Clicks in COWORK Mode

Both human and agent on the same desktop. Agent must wait for a gap.

```
LLM calls Click(x=100, y=200)
    │
    ▼
AgentInputService.click(abs_x, abs_y)
    │
    ├── InputGate.check()
    │       └── mode is COWORK → returns (pass, but caller must schedule)
    │
    ▼
CursorScheduler.submit(CLICK, execute_fn, complexity=1.0)
    │
    ├── Creates Instruction(CLICK, fn, 1.0)
    ├── Appends to FIFO queue
    ├── Blocks caller (instruction.wait())
    │
    ▼
Scheduler dispatch loop (background thread, polling every 5ms):
    │
    ├── Peek instruction from queue
    ├── InputDecayMonitor.agent_can_fire()?
    │       │
    │       ├── Compute: activity *= e^(-λΔt)
    │       ├── activity = 2.3 → threshold is 0.1
    │       └── Returns False (human still active)
    │
    │   ... 200ms passes, human stops typing ...
    │
    ├── InputDecayMonitor.agent_can_fire()?
    │       ├── activity decayed to 0.04
    │       └── Returns True (gap detected!)
    │
    ▼
CursorScheduler._fire(instruction):
    │
    ├── ConflictDetector.check_conflict(100, 200)
    │       ├── GetCursorPos() → human at (500, 300)
    │       ├── WindowFromPoint(500, 300) → HWND 0xABC
    │       ├── WindowFromPoint(100, 200) → HWND 0xDEF
    │       └── Different windows → None (no conflict)
    │
    ├── GhostCursorOverlay.set_state(WORKING)
    │       └── Blue ghost cursor appears at (100, 200)
    │
    ├── ACQUIRE cursor_lock ─────── human cursor frozen
    │
    ├── start_time = now()
    ├── execute_fn()  →  SendInput(click at 100, 200)
    ├── actual_ms = elapsed()
    │
    ├── RELEASE cursor_lock ─────── human cursor unfrozen
    │
    ├── ActionProfiler.record(CLICK, actual_ms)
    │       └── EMA update: adjusts mean and p95 for CLICK
    │
    ├── GhostCursorOverlay.set_state(HIDDEN)
    │
    └── instruction.set_result(success)
            └── submit() unblocks, returns to MCP tool
```

**Modules involved:** InputGate → CursorScheduler → InputDecayMonitor → ConflictDetector → GhostCursorOverlay → cursor_lock → SendInput → ActionProfiler

---

## Scenario 3: Human Presses Ctrl+Alt+Enter (Override)

Human wants control immediately. Agent is mid-work.

```
Human presses Ctrl+Alt+Enter
    │
    ▼
Windows delivers WM_HOTKEY to hidden message window
    │
    ▼
HotkeyService._dispatch_hotkey(OVERRIDE)
    │
    ▼
callback = controller.override     (wired during start())
    │
    ▼
DesktopController.override():
    │
    ├── Acquire controller lock
    │
    ├── Save current mode: _pre_override_mode = AGENT_SOLO
    │
    ├── InputGate.set_mode(HUMAN_OVERRIDE)
    │       │
    │       ├── Store new mode
    │       └── Notify listeners: (AGENT_SOLO → HUMAN_OVERRIDE)
    │
    ├── Was on agent desktop? Yes.
    │       └── DesktopManager.switch_to_user()
    │               └── SwitchDesktop(user_handle)
    │                   Result: user desktop is now input desktop
    │
    └── Release controller lock
```

**Meanwhile, if agent tries to Click:**

```
AgentInputService.click(...)
    │
    ├── InputGate.check()
    │       └── mode is HUMAN_OVERRIDE
    │           → raises AgentPreempted("User has taken control")
    │
    ▼
guarded_tool catches AgentPreempted
    │
    └── format_gate_error(error)
            └── Returns to LLM:
                {"error": "HUMAN_OVERRIDE",
                 "message": "User has taken control. Retry when released."}
```

**LLM sees the error and stops sending input. It can still use Screenshot, Snapshot, etc.**

---

## Scenario 4: Human Releases Override

```
Human presses Ctrl+Alt+Enter again (or Ctrl+Alt+Space to toggle)
    │
    ▼
DesktopController.resume_from_override():
    │
    ├── Check: current mode IS HUMAN_OVERRIDE? Yes.
    │
    ├── Restore: _pre_override_mode was AGENT_SOLO
    │
    ├── InputGate.set_mode(AGENT_SOLO)
    │       └── Mode restored. gate.check() passes again.
    │
    ├── AGENT_SOLO needs agent desktop
    │       └── DesktopManager.switch_to_agent()
    │               └── SwitchDesktop(agent_handle)
    │
    └── Agent can work again. Next MCP tool call succeeds.
```

---

## Scenario 5: Mode Toggle Cycle

```
Human presses Ctrl+Alt+Space repeatedly:

Press 1: AGENT_SOLO → COWORK
    ├── InputGate.set_mode(COWORK)
    └── Stay on agent desktop (COWORK shares it)

Press 2: COWORK → HUMAN_HOME
    ├── InputGate.set_mode(HUMAN_HOME)
    └── DesktopManager.switch_to_user()
        Agent is paused. gate.check() raises AgentPaused.

Press 3: HUMAN_HOME → AGENT_SOLO
    ├── InputGate.set_mode(AGENT_SOLO)
    └── DesktopManager.switch_to_agent()
        Back to full agent control.
```

---

## Scenario 6: Emergency Stop

```
Human presses Ctrl+Alt+S
    │
    ▼
DesktopController.emergency_stop():
    │
    ├── InputGate.set_mode(EMERGENCY_STOP)
    │       └── Terminal state. Can never leave.
    │           gate.check() raises EmergencyStop forever.
    │
    ├── DesktopManager.switch_to_user()
    │       └── User desktop is input desktop
    │
    ├── DesktopManager.destroy()
    │       ├── Terminate all agent processes (Popen.terminate/kill)
    │       └── CloseDesktop(agent_handle)
    │           Agent desktop is gone. All agent windows destroyed.
    │
    └── HotkeyService.stop()
            ├── Post WM_QUIT to listener thread
            ├── Unregister all hotkeys
            └── Destroy hidden window

    Session is over. Must reinitialize to use agent again.
```

---

## Scenario 7: COWORK with Window Conflict

Agent and human both reach for the same window.

```
Human is clicking around in Notepad (HWND 0xABC)
Agent wants to type in Notepad too

CursorScheduler dispatch loop:
    │
    ├── InputDecayMonitor.agent_can_fire()? → True (brief gap)
    │
    ├── ConflictDetector.check_conflict(agent_x, agent_y)
    │       ├── GetCursorPos() → human at (150, 250)
    │       ├── WindowFromPoint(150, 250) → HWND 0xABC (Notepad)
    │       ├── WindowFromPoint(agent_x, agent_y) → HWND 0xABC (Notepad!)
    │       └── SAME HWND → Returns "Notepad"
    │
    └── Agent defers. Does NOT acquire cursor lock.
        Instruction stays in queue.
        Waits until human moves away from Notepad.
```

---

## Scenario 8: Decay Monitor in Detail

Tracking a real typing session:

```
Time 0ms:     Human presses 'H'     → on_input() → activity = 1.0
Time 50ms:    Human presses 'e'     → decay to 0.79, then +1 = 1.79
Time 100ms:   Human presses 'l'     → decay to 1.42, then +1 = 2.42
Time 150ms:   Human presses 'l'     → decay to 1.92, then +1 = 2.92
Time 200ms:   Human presses 'o'     → decay to 2.32, then +1 = 3.32

Time 200ms:   agent_can_fire()? → 3.32 > 0.1 → False

Time 250ms:   (human stops to think)
              decay: 3.32 * e^(-λ*50) = 2.64

Time 350ms:   decay: 2.64 * e^(-λ*100) = 1.67

Time 500ms:   decay: 1.67 * e^(-λ*150) = 0.84

Time 700ms:   decay: 0.84 * e^(-λ*200) = 0.33

Time 1000ms:  decay: 0.33 * e^(-λ*300) = 0.08

Time 1000ms:  agent_can_fire()? → 0.08 < 0.1 → True!
              └── Agent fires instruction into this gap
```

With half_life=150ms, activity halves every 150ms. After ~800ms of silence, the human is considered idle.

---

## Module Responsibility Summary

```
WHO DECIDES WHAT:

"Can the agent send input right now?"
    → InputGate.check()

"Which mode should we be in?"
    → DesktopController (reacts to hotkeys)

"Is the human idle enough for agent to fire?"
    → InputDecayMonitor.agent_can_fire()

"How long will this action take?"
    → ActionProfiler.estimate()

"Execute this action in the next gap"
    → CursorScheduler.submit()

"Are human and agent targeting the same window?"
    → ConflictDetector.check_conflict()

"Which desktop should receive hardware input?"
    → DesktopManager.switch_to_agent() / switch_to_user()

"Show the user where the agent cursor is"
    → GhostCursorOverlay.move_to() / set_state()

"Convert agent errors to LLM-readable responses"
    → format_gate_error()

"Let the LLM check what mode we're in"
    → InputStatus MCP tool
```
