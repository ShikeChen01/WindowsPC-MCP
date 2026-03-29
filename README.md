# WindowsPC-MCP

## Inspiration

[Windows-MCP](https://github.com/almosthumane/Windows-MCP) gives AI agents real desktop control — clicking, typing, launching apps, reading the screen. It's the missing link between LLMs and the Windows GUI.

But it has one fundamental problem: **the agent and the user share the same screen, mouse, and keyboard.** The moment the agent starts working, the user has to sit back and watch. Move the mouse, and you break the agent. Open a window, and the agent gets confused. It's a turn-based system on an OS that was built for multitasking.

This project started with a simple question: *What if the agent had its own monitor?*

## The Problem

When an AI agent operates directly on your desktop:

- **You can't work while the agent works.** Every mouse move or keystroke can derail the agent's actions.
- **The agent can accidentally affect your apps.** A misplaced click lands on your browser instead of the target window.
- **There's no safety boundary.** Global shortcuts like Alt+Tab or Win+D can disrupt the entire desktop session.
- **Recovery is painful.** If the agent loses track of window state, there's no clean way to reset without restarting.

These aren't edge cases — they're the normal experience of running a desktop agent on a shared screen.

## The Solution: Confined Agent Desktop

WindowsPC-MCP creates a **virtual display** using the [Parsec Virtual Display Driver](https://github.com/nomi-san/parsec-vdd) and confines the agent to it at the MCP tool level.

```
┌──────────────────────────────────────────────────────────┐
│  Your Physical Monitors          │  Agent Virtual Screen  │
│                                  │                        │
│  You work here normally.         │  Agent works here.     │
│  Mouse, keyboard, apps —        │  Isolated coordinates.  │
│  all yours.                      │  Filtered shortcuts.    │
│                                  │  Own window space.      │
│                                  │                        │
│  ← Agent can READ all screens    │  ← Agent can only      │
│     for context                  │     WRITE to this one   │
└──────────────────────────────────────────────────────────┘
```

**Key properties:**

- **Agent-relative coordinates.** The agent sees `(0,0)` to `(width, height)`. The confinement engine translates to absolute Windows coordinates. The agent never knows or needs to know where its screen physically sits.
- **Three-level tool confinement.** READ tools (Screenshot, Snapshot) can see all monitors. WRITE tools (Click, Type, Scroll) are bounds-checked to the agent screen. UNCONFINED tools (PowerShell, FileSystem) have no spatial component.
- **Shortcut filtering.** Global shortcuts (Alt+Tab, Win+D, Ctrl+Alt+Del) are blocked. Application shortcuts (Ctrl+S, Ctrl+C, F1–F12) are allowed.
- **State machine with guards.** The server tracks lifecycle states (INIT → READY → DEGRADED → SHUTTING_DOWN). Tools are gated by state — you can't Click before CreateScreen, and read-only tools remain available even in degraded mode.
- **Crash recovery.** Display state is persisted. If the server restarts, it reconnects to the existing virtual display instead of orphaning it.

## Architecture

```
Claude / LLM
    │ stdio or SSE
    ▼
FastMCP Server (__main__.py)
    │
    ├── ServerStateManager      — lifecycle state machine (8 states)
    ├── ConfinementEngine       — coordinate validation, shortcut filtering
    ├── ToolGuard               — pre-execution state + bounds checks
    ├── DisplayManager          — Parsec VDD virtual display lifecycle
    ├── AgentInputService       — input delivery (click, type, scroll)
    ├── TreeService             — UIAutomation tree extraction with labels
    └── Tools (20+)
         ├── CreateScreen / DestroyScreen / ScreenInfo / RecoverWindow
         ├── Screenshot / Snapshot (with UI tree + element labels)
         ├── Click / Type / Move / Scroll / Shortcut
         ├── App / MultiSelect / MultiEdit
         └── PowerShell / FileSystem / Clipboard / Process / Registry / ...
```

## Usage

### Prerequisites

- Windows 10/11
- Python 3.12+
- [Parsec Virtual Display Driver](https://github.com/nomi-san/parsec-vdd) installed (one-time)

### Install

```bash
pip install -e .
```

### Run

```bash
# stdio transport (for Claude Desktop / Claude Code)
windowspc-mcp --transport stdio

# SSE transport (for HTTP clients)
windowspc-mcp --transport sse --host localhost --port 8000
```

### Claude Desktop configuration

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "windowspc-mcp": {
      "command": "windowspc-mcp",
      "args": ["--transport", "stdio"]
    }
  }
}
```

### Agent workflow

```
1. CreateScreen(width=1920, height=1080)   → virtual display appears
2. Screenshot(screen="agent")               → see what's on the agent screen
3. App(name="notepad")                      → launch an app, auto-repositioned to agent screen
4. Snapshot()                               → get UI tree with labeled elements
5. Click(label=3)                           → click element #3 from the snapshot
6. Type(text="Hello from the agent")        → type into the focused element
7. DestroyScreen()                          → clean up when done
```

## Project Structure

```
src/windowspc_mcp/
├── __main__.py              Entry point, FastMCP setup, lifespan
├── server.py                ServerStateManager, state machine
├── confinement/
│   ├── engine.py            ConfinementEngine — bounds validation, coordinate translation
│   ├── guard.py             ToolGuard — state-based access control
│   ├── shortcuts.py         Shortcut blocklist / allowlist
│   ├── decorators.py        guarded_tool, with_tool_name
│   └── errors.py            Error hierarchy
├── display/
│   ├── manager.py           DisplayManager — virtual display lifecycle
│   ├── driver.py            Parsec VDD ctypes wrapper (IOCTL)
│   ├── capture.py           Screen capture (dxcam → mss → Pillow fallback)
│   └── identity.py          Display state persistence
├── input/
│   └── service.py           AgentInputService — click, type, scroll, shortcut
├── tools/                   20+ MCP tool modules
├── tree/
│   ├── service.py           UIAutomation tree crawler
│   ├── views.py             TreeElementNode, ScrollElementNode
│   └── config.py            Control type mappings
└── uia/
    ├── core.py              UIA COM client, INPUT structures
    ├── controls.py          Window enumeration
    └── patterns.py          Invoke, Value, Toggle patterns
```

## License

MIT
