# WindowsMCP Custom — Confined Agent Desktop

**Date:** 2026-03-28
**Status:** Draft
**Approach:** Purpose-built MCP server (Option C)

## Problem

The existing Windows MCP server operates directly on the user's active desktop. The AI agent shares the same mouse, keyboard, and screen as the user — meaning they fight for control. Users cannot work while the agent operates, and the agent can accidentally interact with the user's applications.

## Solution

A custom MCP server that creates a **virtual screen** (via virtual display driver) for the AI agent to operate on. The agent is **confined at the MCP tool level** — it can only send input to its own screen, but can read all screens for context. The user observes and interacts with the agent's screen through a **viewer window** or by switching to it. Both can operate simultaneously with no pausing.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     Windows Desktop Session                      │
│                                                                   │
│  ┌────────────────────┐        ┌────────────────────────────┐   │
│  │  User's Screens    │        │  Agent's Virtual Screen    │   │
│  │  (Physical)        │        │  (IddSampleDriver)         │   │
│  │                    │        │                            │   │
│  │  User's apps       │        │  Agent's apps              │   │
│  │                    │        │  ▲ write-only  ▲ read      │   │
│  │  ┌──────────────┐  │        │  │ (click,     │ (screen-  │   │
│  │  │ Floating     │  │  live  │  │  type,      │  shot)    │   │
│  │  │ Toolbar +  ──┼──┼──feed──┼──│  scroll)    │           │   │
│  │  │ Viewer       │  │        └──┼─────────────┼───────────┘   │
│  │  └──────────────┘  │           │             │               │
│  │                    │           │             │               │
│  │  read-only ◄───────┼───────────┼─────────────┘               │
│  │  (all screens)     │           │                             │
│  └────────────────────┘           │                             │
│                                   │                             │
│  ┌────────────────────────────────┼───────────────────────────┐ │
│  │         Confined MCP Server (FastMCP + Python)             │ │
│  │                                │                           │ │
│  │  ┌────────────┐ ┌─────────────┴──┐ ┌────────────────────┐ │ │
│  │  │ Virtual    │ │ Confinement    │ │ MCP Tools          │ │ │
│  │  │ Display    │ │ Engine         │ │                    │ │ │
│  │  │ Manager    │ │ • bounds check │ │ Screenshot (r:all) │ │ │
│  │  │            │ │ • coord xlate  │ │ Click    (w:agent) │ │ │
│  │  │ • create   │ │ • shortcut     │ │ Type     (w:agent) │ │ │
│  │  │ • destroy  │ │   filter       │ │ App      (w:agent) │ │ │
│  │  │ • config   │ │ • pop-up       │ │ PowerShell (none)  │ │ │
│  │  │ • enum     │ │   detection    │ │ FileSystem (none)  │ │ │
│  │  └────────────┘ └────────────────┘ └────────────────────┘ │ │
│  │                                                           │ │
│  │  stdio/SSE  ◄───────────────────────►  Claude / LLM      │ │
│  └───────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

The system runs as **three components:**

1. **Confined MCP Server** — Python/FastMCP process. All tool logic, confinement engine, virtual display management. Communicates with Claude via stdio or SSE.
2. **Management UI** — Floating toolbar + viewer window. Separate PyQt6 process. Communicates with MCP server via named pipes (status/commands) and shared memory (frame delivery).
3. **Virtual Display Driver** — IddSampleDriver (kernel-mode). One-time install. MCP server controls it via DeviceIoControl to create/destroy virtual monitors.

## Confinement Engine

The confinement engine is the core of the system. Every MCP tool call passes through it before execution.

### Tool Call Flow

```
Claude sends tool call
      │
      ▼
┌─────────────┐
│  MCP Router  │  FastMCP dispatches to tool handler
└──────┬──────┘
       │
       ▼
┌────────────────────────────────────────────────────┐
│              Confinement Engine                      │
│                                                      │
│  1. Get agent screen bounds from Virtual Display Mgr │
│     e.g. { x: 3840, y: 0, w: 1920, h: 1080 }       │
│                                                      │
│  2. Classify tool action:                            │
│     READ  → screenshot, snapshot → allow all screens │
│     WRITE → click, type, move, scroll → check bounds │
│     NONE  → powershell, filesystem → pass through    │
│                                                      │
│  3. For WRITE actions, validate:                     │
│     • Absolute coords must be within agent bounds    │
│     • Element labels resolve then check screen       │
│     • App launch → reposition window to agent screen │
│     • Out of bounds → REJECT with helpful error      │
│                                                      │
│  4. Coordinate translation (agent-relative mode):    │
│     Agent sees (0,0)→(1920,1080) for its screen      │
│     Engine translates to absolute Windows coords     │
│     e.g. agent (500,300) → absolute (4340,300)       │
└──────────────────┬─────────────────────────────────┘
                   │
                   ▼
         ┌─────────────────┐
         │  Execute Action  │  pywin32 / comtypes
         └─────────────────┘
```

### Tool Confinement Matrix

| Tool | Read | Write | Confinement Behavior |
|------|------|-------|---------------------|
| **Screenshot** | all screens | — | Default: agent screen. Optional `screen` param for any/all screens. |
| **Snapshot** | all screens | — | UI tree extraction. Default: agent screen. Can request all. |
| **Click** | — | agent only | Coords validated against agent bounds. Label clicks resolve position first. |
| **Type** | — | agent only | Target element must be on agent screen. |
| **Move** | — | agent only | Cursor movement + drag confined to agent bounds. |
| **Scroll** | — | agent only | Scroll coordinates must be within agent screen. |
| **Shortcut** | — | agent only | Sent to foreground window on agent screen. Global shortcuts blocked. |
| **App** | — | agent only | Launches app, immediately moves window to agent screen. |
| **Wait** | — | — | Pause execution. No confinement — no screen interaction. |
| **MultiSelect** | — | agent only | Multiple clicks/selections. Each coordinate validated against agent bounds. |
| **MultiEdit** | — | agent only | Fill multiple inputs. Each target element must be on agent screen. |
| **Notification** | — | yes | Send Windows toast notifications. No confinement — screen-independent. |
| **Scrape** | yes | — | Fetch web content or browser DOM. No confinement — screen-independent. |
| **PowerShell** | yes | yes | No confinement — screen-independent. |
| **FileSystem** | yes | yes | No confinement — screen-independent. |
| **Clipboard** | yes | yes | Shared clipboard — same desktop session. |
| **Process** | yes | yes | No confinement — screen-independent. |
| **Registry** | yes | yes | No confinement — screen-independent. |

### Coordinate System

**Agent-Relative Mode (Default):** The agent sees its screen as `(0,0)` to `(width, height)`. The confinement engine translates to absolute Windows coordinates. The agent never needs to know where its screen sits in the Windows display layout.

### Shortcut Filtering

Global keyboard shortcuts (`Win+D`, `Alt+Tab`, `Ctrl+Alt+Del`) could affect the entire desktop session. The confinement engine maintains a **blocked shortcut list** for system-wide shortcuts and only allows application-level shortcuts (`Ctrl+C`, `Ctrl+S`, `Alt+F4`) targeted at the foreground window on the agent's screen. The allowlist is configurable.

## Virtual Display Manager

### Lifecycle

```
MCP Server starts
      │
      ▼
┌─────────────────────────────┐
│  Check IddSampleDriver      │
│  • Query device manager      │
│  • If missing → error with   │
│    install instructions       │
└──────────┬──────────────────┘
           │ installed
           ▼
┌─────────────────────────────┐
│  Create Virtual Display      │
│  • DeviceIoControl API       │
│  • Default: 1920×1080        │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│  Detect Screen Position      │
│  • EnumDisplayMonitors       │
│  • Record absolute bounds    │
│  • Expose to Confinement     │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│  Ready — Agent Can Operate   │
└──────────┬──────────────────┘
           │ on shutdown
           ▼
┌─────────────────────────────┐
│  Cleanup                     │
│  • Move windows to user's    │
│    screen                    │
│  • Remove virtual display    │
│  • Release driver handle     │
└─────────────────────────────┘
```

### IddSampleDriver

An open-source Indirect Display Driver (IDD) for Windows 10/11. Creates virtual monitors that Windows treats as real displays — they appear in Display Settings, support hardware acceleration, and work with all apps. Most mature open-source IDD with active development. Supports dynamic creation/destruction via DeviceIoControl without reboot.

**One-time install:** User installs the driver once (signed `.inf` + `.sys`). The MCP server manages it programmatically after that.

### Display Configuration

| Setting | Default | Notes |
|---------|---------|-------|
| Resolution | `1920×1080` | Capped for token efficiency. Configurable down to 1280×720. |
| DPI Scaling | `100%` | Fixed to avoid coordinate scaling complexity. |
| Position | `auto` | Placed right of the rightmost physical monitor. User can reposition in Display Settings. |
| Refresh Rate | `30 Hz` | Agent doesn't need high FPS. Lower rate reduces GPU load. |

### Display Management MCP Tools

| Tool | Description |
|------|-------------|
| **CreateScreen** | Create the agent's virtual display. Params: resolution (optional). Returns screen bounds. |
| **DestroyScreen** | Remove the virtual display. Moves remaining windows to user's primary screen first. |
| **ScreenInfo** | Returns agent screen bounds, resolution, and list of all screens with roles. |
| **RecoverWindow** | Move a window (by title/handle) from any screen to the agent's screen. For stray pop-ups. |

## Management UI

Separate PyQt6 process with two components: a floating toolbar and a viewer window.

### Floating Toolbar (Always-on-Top)

A compact, draggable, always-on-top widget on the user's desktop:

- **Live mini-preview** — Thumbnail of agent's screen updated in real-time. Click to open full viewer.
- **Status dashboard** — MCP connection state, agent screen resolution, last tool action with timestamp.
- **Screen controls** — Create/destroy agent screen buttons. Destroy gracefully migrates windows first.
- **Open Viewer button** — Launches the full viewer window.

### Viewer Window (Resizable)

A resizable window showing a live feed of the agent's virtual screen:

- **Interactive** — Click and type through the viewer. Mouse and keyboard events translated to absolute coordinates on the virtual display. Agent and user can operate simultaneously.
- **Display modes:**
  - **Fit** — Scale agent screen to viewer window size.
  - **1:1** — Actual pixels, scrollable if viewer is smaller.
  - **Fullscreen** — Borderless on any monitor. Looks like a dedicated agent screen.
- **Live capture** — Captures virtual display region at 30fps via dxcam/BitBlt. GPU-backed rendering.
- **Action overlay (optional)** — Semi-transparent overlay showing agent's last action: click location with ripple, typed text, scroll direction.

### IPC Architecture

```
UI Process (PyQt6)                    MCP Server Process
┌───────────────────────┐             ┌──────────────────┐
│  Toolbar Widget       │◄── IPC ────►│  Status Publisher │
│  • mini preview       │  (named     │  • connection     │
│  • status display     │   pipe)     │  • last action    │
│  • control buttons    │             │  • screen bounds  │
│                       │             │                   │
│  Viewer Widget        │◄── frame ──│  Screen Capturer  │
│  • render frames      │   stream   │  • dxcam capture  │
│  • forward input      │  (shared   │  • encode frames  │
│  • display modes      │   memory)  │                   │
└───────────────────────┘             └──────────────────┘
```

- **Shared memory** for frame delivery (zero-copy overhead)
- **Named pipes** for status updates and commands (low-frequency JSON messages)
- **Named pipes** for input forwarding (viewer → MCP → pywin32)

## Error Handling

### Pop-ups Land on User's Screen

Windows places dialogs on the "primary" monitor, not necessarily where the parent app lives.

- **Detection:** Agent periodically screenshots all screens, or on failed interaction. Confinement engine flags when an expected dialog isn't found on agent screen.
- **Recovery:** `RecoverWindow` tool moves the stray window to agent screen. System prompt instructs agent to check other screens when an expected dialog doesn't appear.

### Apps Launch on Wrong Screen

Windows remembers last window position. New app windows may open on user's screen.

- **Prevention:** `App` tool immediately moves + resizes the new window to agent screen after launch. Short polling loop (100ms intervals, 3s timeout) to catch the window handle.
- **Fallback:** If window handle not found in time, scan all screens and use `RecoverWindow`.

### Virtual Display Driver Missing

- **Detection:** MCP server checks for driver on startup via device enumeration.
- **Response:** Returns clear error with install instructions. Non-screen tools (PowerShell, FileSystem) still work.

### Display Creation Fails

- **Detection:** `CreateScreen` returns error with specific failure reason.
- **Recovery:** Retry once after 1s delay. If still failing, report diagnostics (driver version, GPU info, existing virtual displays).

### Out-of-Bounds Action Attempt

- **Response:** Confinement engine rejects immediately. Returns error with valid bounds and attempted coordinates.
- **No clamping:** Coordinates are NOT silently clamped to screen edges. Explicit rejection teaches the agent the boundary.

### Global Shortcut Attempted

- **Response:** Shortcut blocked. Error suggests alternatives (e.g., use `App` tool instead of `Alt+Tab`).
- **Allowlist:** App-level shortcuts always allowed. Configurable for edge cases.

### MCP Server Crash

- **Virtual display persists:** IddSampleDriver display survives process death. Windows and apps on agent screen stay put.
- **Recovery:** Toolbar detects disconnect, shows status. On restart, server re-discovers existing virtual display and reconnects without recreating screen.

### Display Layout Changes

- **Detection:** Listen for `WM_DISPLAYCHANGE` messages. Re-enumerate monitors.
- **Response:** Update agent screen bounds (position may shift). Notify agent via next tool response.

## Tech Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| MCP Framework | `FastMCP` | Same as existing Windows MCP. Proven, async, handles stdio/SSE. |
| UI Automation | `comtypes` (UIAutomation COM) | Element discovery, accessibility tree, focus tracking. |
| Screenshots | `dxcam` → `mss` → `Pillow` | Fallback chain. dxcam for GPU-accelerated capture. |
| Win32 APIs | `pywin32` | Window management, input injection, display enumeration. |
| Virtual Display | `IddSampleDriver` + `ctypes` | DeviceIoControl via ctypes for virtual monitor management. |
| Management UI | `PyQt6` | Native look, hardware-accelerated viewer rendering. |
| IPC | Named pipes + shared memory | Zero-copy frames, low-frequency status messages. |
| Package Manager | `uv` | Fast Python package management. Same as existing Windows MCP. |

## Project Structure

```
WindowsMCP_Custom/
├── src/
│   └── windowsmcp_custom/
│       ├── __main__.py              # Entry point, register tools on FastMCP
│       ├── confinement/
│       │   ├── engine.py            # Confinement engine — bounds check, coord translation
│       │   ├── shortcuts.py         # Shortcut allowlist/blocklist
│       │   └── bounds.py            # Screen bounds tracking, WM_DISPLAYCHANGE listener
│       ├── display/
│       │   ├── manager.py           # Virtual display lifecycle (create/destroy/enum)
│       │   ├── driver.py            # IddSampleDriver DeviceIoControl wrapper
│       │   └── capture.py           # Screen capture (dxcam/mss/Pillow fallback)
│       ├── tools/
│       │   ├── screenshot.py        # Screenshot + Snapshot (read: all screens)
│       │   ├── input.py             # Click, Type, Move, Scroll, Shortcut, Wait (write: agent)
│       │   ├── multi.py             # MultiSelect, MultiEdit (write: agent)
│       │   ├── app.py               # App launch + reposition to agent screen
│       │   ├── screen.py            # CreateScreen, DestroyScreen, ScreenInfo, RecoverWindow
│       │   ├── shell.py             # PowerShell (pass-through)
│       │   ├── filesystem.py        # FileSystem (pass-through)
│       │   ├── clipboard.py         # Clipboard (pass-through)
│       │   ├── process.py           # Process (pass-through)
│       │   ├── registry.py          # Registry (pass-through)
│       │   ├── notification.py      # Toast notifications (pass-through)
│       │   └── scrape.py            # Web scraping (pass-through)
│       ├── uia/
│       │   ├── core.py              # UIAutomation COM wrapper
│       │   ├── controls.py          # Control-specific logic
│       │   └── patterns.py          # UIA patterns (scroll, invoke, etc.)
│       └── ipc/
│           ├── status.py            # Named pipe server for status publishing
│           ├── frames.py            # Shared memory frame buffer
│           └── commands.py          # Named pipe for UI commands/input
├── ui/
│   ├── main.py                      # UI process entry point
│   ├── toolbar.py                   # Floating toolbar widget
│   ├── viewer.py                    # Viewer window with interactive mode
│   └── resources/                   # Icons, styles
├── driver/
│   └── README.md                    # IddSampleDriver install instructions
├── tests/
│   ├── test_confinement.py
│   ├── test_display.py
│   ├── test_tools.py
│   └── test_ipc.py
├── docs/
├── pyproject.toml
└── README.md
```

## Dependencies

### Runtime
- Python 3.13+
- FastMCP
- comtypes >= 1.4.15
- dxcam >= 0.3.0
- pywin32 >= 311
- PyQt6
- Pillow
- mss
- thefuzz (fuzzy string matching for element labels)

### System
- Windows 10/11
- IddSampleDriver (one-time install)
- GPU with WDDM 2.0+ driver (for dxcam and virtual display)

## Non-Goals

- No remote mode or cloud VM support (use the original Windows MCP for that)
- No telemetry or analytics
- No authentication layer
- No browser DOM extraction (may add later if needed)
- No multi-agent support (one agent screen per MCP server instance)
