# WindowsPC-MCP v0.2.0 — Independent Agent Input

**Date:** 2026-03-31
**Status:** Design Complete
**Supersedes:** PostMessage approach (2026-03-29, rejected — 30-70% app compat too low)

---

## Problem

Agent and user share one cursor, one keyboard focus, and one desktop. SendInput is global — every agent click physically moves the user's cursor, every agent keystroke steals focus. User cannot work while the agent operates. This is the single biggest usability blocker.

## Solution

Two-layer input isolation:

1. **Desktop isolation** — CreateDesktop gives the agent its own Win32 desktop with independent cursor, focus chain, and keyboard state. ~99% app compatibility (same as SendInput).
2. **Cursor scheduling** — In COWORK mode, a time-sharing scheduler lets both actors use a shared desktop by slotting agent operations into detected human idle gaps.

---

## Operating Modes

```
AGENT_SOLO ◄────► COWORK ◄────► HUMAN_HOME
     │                │               │
     └───────► HUMAN_OVERRIDE ◄───────┘
                      │
              EMERGENCY_STOP ◄── from anywhere
```

### AGENT_SOLO

Agent's desktop is the input desktop. Agent has full uncontested SendInput access. User watches via a streaming viewer window on their own desktop. No scheduling overhead. Best for long autonomous tasks.

### COWORK

Both actors on the same desktop. Agent fires instructions into human idle gaps detected by exponential decay. During agent execution, human cursor is locked (typically <5ms per click). Human reclaims cursor automatically when instruction completes. Best for collaborative work.

### HUMAN_OVERRIDE

Hotkey-triggered from any mode. Agent is immediately blocked — all pending and in-flight operations are rejected with `AgentPreempted`. Human has full control. Agent resumes only when human explicitly releases via hotkey. Best for quick manual corrections.

### HUMAN_HOME

User's own desktop is the input desktop. Agent is paused entirely (queue drains, no new operations accepted). Normal user workflow. Agent can be sent back to work via hotkey.

### EMERGENCY_STOP

Accessible from all states. Kills all pending agent MCP operations. Forces switch to user's desktop. Terminates the agent input session. No recovery — must reinitialize.

---

## Privilege Hierarchy

```
LEVEL 0 — EMERGENCY STOP
    RegisterHotKey on all desktops.
    Cannot be blocked or queued behind agent work.
    Always wins. Kills session.

LEVEL 1 — HUMAN INPUT
    Physical mouse/keyboard.
    In COWORK: cursor locked only during agent execution (<5ms typical).
    Hotkey override is instant from any mode.

LEVEL 2 — AGENT INPUT
    Programmatic SendInput via MCP tools.
    In AGENT_SOLO: unrestricted.
    In COWORK: scheduled, fires only in detected idle gaps.
    In HUMAN_OVERRIDE/HOME: blocked.
```

---

## Component Architecture

```
MCP Tools (Click, Type, Move, Scroll, Shortcut, ...)
        │
        ▼
┌─────────────────────────────────────────────┐
│                 InputGate                    │
│                                             │
│  Routes based on current mode:              │
│  AGENT_SOLO  → SendInput (direct)           │
│  COWORK      → CursorScheduler              │
│  HUMAN_*     → reject (AgentPreempted)      │
│  EMERGENCY   → reject (EmergencyStop)       │
└───────────────────┬─────────────────────────┘
                    │ (COWORK path)
                    ▼
┌─────────────────────────────────────────────┐
│              CursorScheduler                 │
│                                             │
│  InputDecayMonitor — gap detection          │
│  ActionProfiler    — execution cost         │
│  InstructionQueue  — FIFO pending ops       │
│  CursorLock        — exclusive execution    │
└───────────────────┬─────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────┐
│             DesktopManager                   │
│                                             │
│  Desktop lifecycle (create/destroy/switch)   │
│  Process launcher (STARTUPINFO.lpDesktop)    │
│  StreamingViewer (capture → viewer window)   │
└─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────┐
│              HotkeyService                   │
│                                             │
│  Registered on ALL desktops                  │
│  High-priority listener thread               │
│  Mode transitions + emergency stop           │
└─────────────────────────────────────────────┘
```

---

## Desktop Isolation Layer

### What CreateDesktop provides

Each Win32 desktop is an independent UI namespace. The agent's desktop has:

- **Its own cursor** — independent position and state
- **Its own focus chain** — which window is active
- **Its own keyboard state** — key up/down tracking
- **Its own window set** — only agent-launched apps are visible
- **Its own hooks** — SetWindowsHookEx is per-desktop

### What is shared (same session, same user)

- Filesystem — same drives, paths, files
- Registry — same HKCU, HKLM
- Process table — processes can span desktops
- Network — same connections, ports
- RAM / CPU — same resource pool, no isolation
- User profile — same settings, same Chrome profile

This is the right tradeoff. The agent needs shared file access and app settings. Full session isolation (RDP) was rejected for this reason.

### DesktopManager

Responsibilities:

1. **Create agent desktop** — `CreateDesktop("AgentDesktop", ...)` at session start. Desktop persists for the session lifetime.
2. **Switch input desktop** — `SwitchDesktop(hDesktop)` to transfer which desktop receives hardware input. Only one desktop is the input desktop at a time.
3. **Launch processes on agent desktop** — Set `STARTUPINFO.lpDesktop = "AgentDesktop"` when spawning apps. The app's windows appear on the agent desktop, not the user's.
4. **Destroy** — `CloseDesktop` on session end or emergency stop.

### Desktop streaming

The user needs to see what the agent is doing. A viewer window on the user's desktop shows a live capture of the agent's desktop.

Capture options (in order of preference):
- **DXGI Desktop Duplication** — GPU-accelerated, lowest latency, works with Parsec VDD
- **BitBlt from desktop DC** — simpler fallback, higher CPU
- **Shared memory / named pipe** — if the agent process renders frames directly

The viewer is a standard Win32 window on the user's desktop. Click-through optional (clicking the viewer could route to the agent desktop as a COWORK entry point).

### Single-instance app handling

Apps like Chrome and VS Code detect existing instances and route new windows to the running process on the user's desktop. Mitigation:

- Launch with separate profile flags: `--user-data-dir=` for Chrome
- Set environment variables that force new instances
- Accept that some apps will resist — document which ones

### No shell on agent desktop

The agent desktop has no taskbar, no Start menu, no Explorer shell. This is intentional — the agent launches apps explicitly via MCP tools. A blank desktop is less confusing for the agent.

---

## Cursor Scheduling Layer (COWORK Mode)

### The scheduling problem

In COWORK mode, both actors use the same desktop. Windows has one cursor per desktop. We time-share it.

**Principle:** Both actors are bursty and discrete. Humans have natural gaps between interactions (typing pauses, reading, thinking). Agent operations are atomic and short. We detect gaps and slot agent ops into them.

**Rule: when the agent fires, human is locked out. When human is active, agent waits. Hotkey overrides everything.**

### Gap detection — Exponential decay

A single floating-point variable `activity` tracks human input intensity.

**On every human input event (key press, mouse move, click):** `activity += 1.0`

**Continuously:** `activity` decays by `e^(-λΔt)` where `λ = ln(2) / half_life`

**Agent can fire when:** `activity < threshold`

Parameters:
- `half_life` — How fast activity decays. 150ms detects brief typing pauses. 300ms waits for real idle moments. Default: 150ms.
- `threshold` — Below this, gap is declared. Default: 0.1.

```
Human input:  ↓ ↓↓ ↓↓↓  ↓ ↓              ↓↓  ↓
activity:    ─╱╲╱╲╱╲╱╲──╱╲╱╲──────────────╱╲──╱╲─
threshold ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─╲─ ─ ─ ─ ─ ─ ─ ─
                                  ╲________╱
                                   AGENT
                                   FIRES
```

No history buffer. No sliding window. No prediction model. The decay is the prediction — when activity is below threshold, the gap is here.

**Future ML hook:** Make `half_life` and `threshold` adaptive. A lightweight model trained on per-user input patterns (time-of-day, app-specific rates, typing vs mousing bursts) adjusts these two parameters. The equation and interface are unchanged. The predictor becomes a parameter tuner, not a replacement.

### Action profiler

The scheduler needs to know how long an agent instruction will take before deciding to fire it.

**Startup calibration:**
- Benchmark every action type: move, click, double-click, single keystroke, string (4 chars), scroll
- 20 samples each
- Record mean and p95 per action type

**Runtime adjustment:**
- After every execution, record actual time
- Update estimates via exponential moving average (α = 0.2)
- The profiler self-corrects as real-world costs diverge from calibration

**Estimation:**
- Use p95 (conservative) as base cost
- Scale by instruction complexity: click = 1x, type_string = (length / 4)x, drag = 3x
- The scheduler compares estimated cost against gap availability

### Dispatch loop

```
Agent instruction arrives via MCP tool
        │
        ▼
   Enqueue (FIFO)
        │
        ▼
   ┌─ activity < threshold? ─┐
   │                          │
   YES                        NO
   │                          │
   ▼                          ▼
   Estimate cost            Poll every 5ms
   of instruction           for decay to cross
   │                          │
   ▼                          │
   ACQUIRE CURSOR LOCK        │
   │                          │
   Human cursor frozen.       │
   Execute instruction.       │
   Record actual time → profiler.
   │                          │
   RELEASE CURSOR LOCK        │
   │                          │
   Human cursor unfrozen.     │
   Dequeue. Next instruction. ┘
```

### Cursor lock contract

- **While held:** Human physical input is queued by the OS, not dropped. The cursor doesn't move. Human sees a momentary freeze.
- **Typical duration:** <1ms for move, <3ms for click, <5ms for short string, up to 50ms for long type operations.
- **Non-reentrant:** One instruction at a time. Back-to-back agent instructions release the lock between each, giving human a window to reclaim.
- **Lock scope:** Only the cursor lock. Keyboard events during agent execution are queued normally and delivered when lock releases.

### Human experience during agent execution

```
Agent fires a click (~3ms):

Human cursor: [normal] → [frozen 3ms] → [normal]
Human keyboard: [normal — always works, just queued briefly]
Visual feedback: Ghost cursor overlay shows agent's target

Agent fires type_string("hello world", ~25ms):

Human cursor: [normal] → [frozen 25ms] → [normal]
Human keyboard: [queued 25ms, then delivered]
Visual feedback: Ghost cursor at text field, agent cursor icon
```

For typical operations, the freeze is imperceptible. For longer type operations, the user may notice a brief hitch — this is the accepted tradeoff.

### Ghost cursor overlay

In COWORK mode, a visual overlay shows the non-active actor's cursor position.

- **Layered window** (WS_EX_LAYERED) — transparent background
- **Click-through** (WS_EX_TRANSPARENT) — doesn't intercept input
- **Always on top** (WS_EX_TOPMOST) — visible above all windows
- **Distinct icon** — colored differently from system cursor (blue for agent, etc.)

The ghost shows:
- Agent's tracked position when human is active
- Human's last position when agent is executing (briefly, during lock)

States:
- Blue cursor = agent working
- Gray cursor = agent waiting for gap
- Hidden = agent idle (no pending instructions)

### Window conflict detection

Beyond cursor scheduling, we detect when both actors target the same window.

If the human is interacting with a window and the agent's next instruction targets the same HWND, the agent defers entirely. No interleaved input on the same window — too unpredictable.

Detection: compare `WindowFromPoint(human_cursor_pos)` against the agent instruction's target HWND. If they match, agent waits until human moves away or a timeout triggers `AgentDeferred`.

---

## Hotkey System

### Registration

Hotkeys are registered via `RegisterHotKey` on a hidden message window on each desktop. The listener runs on a high-priority thread — not gated behind any agent work.

| Hotkey | Registered on | Action |
|--------|--------------|--------|
| Ctrl+Alt+Space | All desktops | Toggle: cycle AGENT_SOLO → COWORK → HUMAN_HOME |
| Ctrl+Alt+Enter | All desktops | HUMAN_OVERRIDE (instant, from any mode) |
| Ctrl+Alt+Break | All desktops | EMERGENCY_STOP |
| Ctrl+Alt+Home | Agent desktop | Switch to HUMAN_HOME |

### Mode transition behavior

**Any → HUMAN_OVERRIDE:**
1. Set InputGate mode to HUMAN_OVERRIDE
2. If cursor lock is held (agent mid-execution): wait for current instruction to complete (bounded by profiled max, typically <50ms), then block further instructions
3. All queued instructions receive `AgentPreempted` error
4. LLM sees the error and knows to pause

**Any → EMERGENCY_STOP:**
1. Set InputGate mode to EMERGENCY
2. If cursor lock is held: force-release (agent instruction may be torn — accepted)
3. Kill all pending MCP operations
4. SwitchDesktop to user's desktop
5. Session is terminated — requires reinitialization

**HUMAN_OVERRIDE → resume (COWORK or AGENT_SOLO):**
1. Human presses toggle hotkey
2. InputGate mode updated
3. Agent's next MCP call succeeds normally
4. Queued instructions begin dispatching

---

## MCP Tool Integration

### InputGate — routing layer

Every MCP tool that performs input (Click, Type, Move, Scroll, Shortcut, MultiEdit, MultiSelect) passes through InputGate before executing.

InputGate checks the current mode and routes:

| Mode | Behavior |
|------|----------|
| AGENT_SOLO | Pass through to SendInput on agent desktop. No scheduling. |
| COWORK | Submit to CursorScheduler. Blocks until scheduled and executed. |
| HUMAN_OVERRIDE | Reject immediately: `{"error": "HUMAN_OVERRIDE", "message": "User has taken control. Retry when released."}` |
| HUMAN_HOME | Reject: `{"error": "AGENT_PAUSED", "message": "Agent is paused. Waiting for user to resume."}` |
| EMERGENCY_STOP | Reject: `{"error": "EMERGENCY_STOP", "message": "Session terminated by user."}` |

### Non-input tools

Tools that don't touch the cursor (Screenshot, Snapshot, Scrape, FileSystem, PowerShell, Process, Registry, Clipboard, App, Notification) are **not gated** by InputGate. They work in all modes. The agent can still observe and think while paused — it just can't send input.

### LLM-visible state

A new MCP tool `InputStatus` exposes the current mode to the LLM:

```json
{
  "mode": "COWORK",
  "agent_can_input": true,
  "queue_depth": 0,
  "human_activity": 0.03,
  "last_preemption": null
}
```

The LLM can check this before planning input-heavy sequences, or react to preemption errors by switching to observation-only work.

---

## Resource Considerations

CreateDesktop shares all system resources (CPU, RAM, disk, network). There is no per-desktop resource isolation.

**Implications:**
- Each app the agent launches consumes real CPU/RAM
- A runaway agent process can starve user's apps
- Emergency stop should kill agent-launched processes, not just pause them

**Mitigations (future):**
- Use Job Objects to cap CPU/memory for agent-launched processes
- Monitor total agent resource usage and expose via InputStatus
- Not required for v0.2.0 — agent runs a handful of lightweight apps

---

## Rejected Approaches

| Approach | Why rejected |
|----------|-------------|
| **PostMessage only** | 30-70% app compatibility — too many apps ignore posted input events |
| **Virtual HID (vmulti, Interception)** | Windows merges all mice into one cursor per desktop — doesn't solve the problem |
| **Touch injection (CreateSyntheticPointerDevice)** | Independent pointers but ~70% app compat, different input semantics |
| **Separate RDP session** | Too heavy — separate user profile, settings, no shared Chrome data |
| **Sub-millisecond cursor swapping** | Overengineered — simpler to just lock briefly during agent execution |

---

## Open Questions

1. **COWORK cursor lock feedback** — Should the user see a visual indicator when cursor is locked during agent execution? A brief border flash or icon change could prevent confusion. Low priority — the lock is typically imperceptible.

2. **Agent desktop resolution** — Should the agent desktop match the Parsec VDD virtual display resolution, or be independent? Matching simplifies coordinate mapping.

3. **Streaming viewer interaction** — Can clicking in the streaming viewer window route input to the agent desktop? This would provide a COWORK entry point without hotkeys. Risk: accidental input forwarding.

4. **Process cleanup on mode switch** — When switching from AGENT_SOLO to HUMAN_HOME, should agent-launched processes be killed, suspended, or left running? Left running is simplest but wastes resources.

5. **Adaptive decay parameters** — The ML hook for adaptive `half_life` and `threshold` is spec'd as a future enhancement. What data would we collect for training? Input event timestamps with gap/execution outcome labels.

---

## Implementation Order

### Phase 1: Desktop isolation (AGENT_SOLO + HUMAN_HOME)

1. DesktopManager — create/destroy/switch agent desktop
2. Process launcher — STARTUPINFO.lpDesktop integration
3. HotkeyService — basic mode toggle (AGENT_SOLO ↔ HUMAN_HOME)
4. Desktop streaming — capture agent desktop, render in viewer
5. InputGate — route based on mode, pass-through for AGENT_SOLO

Delivers: agent and user fully isolated. Agent works on own desktop. User watches via stream. No cursor conflict possible.

### Phase 2: Emergency stop + override

6. EMERGENCY_STOP hotkey — kill ops, force switch, terminate session
7. HUMAN_OVERRIDE mode — instant block, clean resume
8. Error responses — LLM-visible preemption signals
9. InputStatus tool — expose mode to LLM

Delivers: human can always interrupt. LLM reacts to preemption gracefully.

### Phase 3: COWORK mode

10. InputDecayMonitor — exponential decay gap detection
11. ActionProfiler — startup calibration + runtime adjustment
12. CursorScheduler — dispatch loop with cursor lock
13. Ghost cursor overlay — visual feedback for both actors
14. Window conflict detection — same-window deference
15. InputGate COWORK routing — submit to scheduler

Delivers: both actors on same desktop, time-shared cursor, human-priority scheduling.

### Phase 4: Polish + future hooks

16. Adaptive parameter interface — ML-ready tuning for decay parameters
17. Resource monitoring — Job Objects for agent process caps
18. Viewer interaction — click-to-forward from streaming window
19. Configurable hotkeys — user can rebind
