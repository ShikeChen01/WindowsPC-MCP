# Desktop Package — Architecture Overview

The `desktop/` package implements independent agent input: desktop isolation, mode management, COWORK cursor scheduling, and visual feedback.

## Module Map

```text
desktop/
├── manager.py      Win32 desktop lifecycle (CreateDesktop/Switch/Close)
├── hotkeys.py      Global hotkeys (Ctrl+Alt+Space/Enter/Break)
├── gate.py         Mode enum + input routing (pass/block/queue)
├── controller.py   Orchestrates mode transitions across all components
├── monitor.py      Exponential decay — detects human idle gaps
├── profiler.py     Action timing — calibration + runtime EMA
├── scheduler.py    COWORK dispatch loop with cursor lock
├── overlay.py      Ghost cursor overlay + window conflict detection
├── responses.py    MCP error formatting for preempted states
└── (tools/input_status.py)  InputStatus MCP tool
```

## Dependency Graph

```text
controller.py
├── manager.py       (desktop lifecycle)
├── hotkeys.py       (hotkey callbacks)
└── gate.py          (mode state)

scheduler.py
├── monitor.py       (gap detection)
└── profiler.py      (timing estimates)

overlay.py           (standalone — Win32 only)
responses.py         (standalone — error mapping only)
input_status.py      (reads gate.py)
```

No circular dependencies. Each module has a single responsibility.

## Operating Modes

```text
AGENT_SOLO ◄───► COWORK ◄───► HUMAN_HOME
     │               │              │
     └──────► HUMAN_OVERRIDE ◄─────┘
                     │
             EMERGENCY_STOP ◄── from anywhere (terminal)
```

## Thread Model

| Thread | Owner | Purpose |
|--------|-------|---------|
| Main (MCP) | FastMCP | Tool execution, submit() calls |
| Hotkey listener | HotkeyService | Win32 message pump, fires callbacks |
| Cursor scheduler | CursorScheduler | Polls for gaps, dispatches instructions |
| (Future) Raw input | InputDecayMonitor | Feeds human events to decay monitor |

## Per-Module Docs

- [01-manager.md](01-manager.md) — DesktopManager
- [02-hotkeys.md](02-hotkeys.md) — HotkeyService
- [03-gate.md](03-gate.md) — InputGate + InputMode
- [04-controller.md](04-controller.md) — DesktopController
- [05-monitor.md](05-monitor.md) — InputDecayMonitor
- [06-profiler.md](06-profiler.md) — ActionProfiler
- [07-scheduler.md](07-scheduler.md) — CursorScheduler
- [08-overlay.md](08-overlay.md) — GhostCursorOverlay + ConflictDetector
- [09-responses.md](09-responses.md) — Error responses + InputStatus
