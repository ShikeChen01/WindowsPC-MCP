# Tool Reference

Complete reference for all 23 WindowsPC-MCP tools. Parameters marked with `=` have defaults and are optional.

---

## Screen Management

### CreateScreen

Create the agent's virtual display.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `width` | int | 1920 | Display width, clamped to [1280, 1920] |
| `height` | int | 1080 | Display height, clamped to [720, 1080] |

```
CreateScreen()
CreateScreen(width=1280, height=720)
```

Must be called before any GUI tool (Click, Type, Screenshot, etc.) will work. Raises an error if a display already exists.

---

### DestroyScreen

Destroy the virtual display and release its bounds. Takes no parameters.

```
DestroyScreen()
```

After calling this, GUI tools are disabled until `CreateScreen` is called again. Read-only tools (ScreenInfo) still work.

---

### ScreenInfo

List all monitors currently active on the system. Takes no parameters.

```
ScreenInfo()
```

Returns a numbered list of monitors with resolution and position. The agent screen (if any) is marked with `[AGENT]`.

---

### RecoverWindow

Find windows matching selectors and move them onto the agent screen.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `title` | str | None | Regex pattern to match window titles |
| `pid` | int | None | Match by process ID |
| `process_name` | str | None | Match by process name (substring, case-insensitive) |
| `class_name` | str | None | Match by window class name |

```
RecoverWindow(title="Notepad")
RecoverWindow(process_name="chrome")
RecoverWindow(pid=1234)
```

At least one selector is required. Fails if more than 5 windows match (to prevent accidental bulk moves).

---

## Vision

### Screenshot

Capture a screenshot.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `screen` | str | "agent" | `"agent"` for agent screen, `"all"` for every monitor, or an integer index |

```
Screenshot()
Screenshot(screen="all")
Screenshot(screen="1")
```

Returns base64-encoded JPEG image(s) with monitor descriptions.

---

### Snapshot

Capture a screenshot plus a structured summary of visible windows and interactive UI elements.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `screen` | str | "agent" | Same as Screenshot |

```
Snapshot()
Snapshot(screen="all")
```

Returns:
- Screenshot image (JPEG)
- Window list with titles, positions, and class names
- Interactive elements list with numbered labels (for use with `Click(label=N)` and `Type(label=N)`)
- Scrollable elements list

This is the primary tool for understanding screen state. The numbered labels persist until the next Snapshot call.

---

## Input

### Click

Click at a position on the agent screen.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `x` | int | None | Agent-relative X coordinate |
| `y` | int | None | Agent-relative Y coordinate |
| `button` | str | "left" | `"left"`, `"right"`, or `"middle"` |
| `clicks` | int | 1 | Number of clicks (2 for double-click) |
| `label` | int | None | Element label from Snapshot (overrides x/y) |

```
Click(x=100, y=200)
Click(label=3)
Click(x=100, y=200, button="right")
Click(x=100, y=200, clicks=2)
```

Either `x`/`y` or `label` is required. When using `label`, coordinates are resolved from the latest Snapshot's element list.

---

### Type

Type text, optionally clicking a target first.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `text` | str | *required* | Text to type |
| `x` | int | None | Click here first before typing |
| `y` | int | None | Click here first before typing |
| `clear` | bool | False | Clear existing content before typing |
| `caret_position` | str | "idle" | Move caret to `"start"`, `"end"`, or `"idle"` (no move) |
| `press_enter` | bool | False | Press Enter after typing |
| `label` | int | None | Element label from Snapshot (overrides x/y) |

```
Type(text="Hello world")
Type(text="Hello", x=100, y=200)
Type(text="Hello", label=5, clear=True, press_enter=True)
```

---

### Move

Move the mouse cursor.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `x` | int | *required* | Agent-relative X coordinate |
| `y` | int | *required* | Agent-relative Y coordinate |
| `drag` | bool | False | Hold left button during the move |

```
Move(x=500, y=300)
Move(x=500, y=300, drag=True)
```

---

### Scroll

Scroll at a position.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `x` | int | *required* | Agent-relative X coordinate |
| `y` | int | *required* | Agent-relative Y coordinate |
| `amount` | int | -3 | Wheel detents. Negative = down/left, positive = up/right |
| `horizontal` | bool | False | Scroll horizontally instead of vertically |

```
Scroll(x=500, y=300)
Scroll(x=500, y=300, amount=5)
Scroll(x=500, y=300, horizontal=True)
```

---

### Shortcut

Send a keyboard shortcut.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `keys` | str | *required* | Plus-separated key names |

```
Shortcut(keys="ctrl+s")
Shortcut(keys="ctrl+shift+t")
Shortcut(keys="f5")
Shortcut(keys="alt+f4")
```

**Blocked shortcuts** (rejected with an error): Alt+Tab, Win+D, Win+L, Ctrl+Alt+Del, and other global shortcuts that would affect the user's desktop session.

**Allowed shortcuts**: Application-level shortcuts like Ctrl+S, Ctrl+C, Ctrl+V, Ctrl+Z, F1-F12, etc.

---

### Wait

Pause execution.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `seconds` | float | 1.0 | Duration in seconds, clamped to [0.1, 30] |

```
Wait()
Wait(seconds=3)
```

---

## Batch Input

### MultiSelect

Click multiple positions in sequence.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `positions` | list | *required* | List of `[x, y]` pairs |
| `button` | str | "left" | `"left"`, `"right"`, or `"middle"` |

```
MultiSelect(positions=[[100, 200], [300, 400], [500, 600]])
```

Stops on the first confinement error (coordinate out of bounds).

---

### MultiEdit

Click and type into multiple fields in sequence.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `fields` | list | *required* | List of dicts with `x`, `y`, `text` keys |

```
MultiEdit(fields=[
    {"x": 100, "y": 200, "text": "John"},
    {"x": 100, "y": 250, "text": "Doe"},
    {"x": 100, "y": 300, "text": "john@example.com"}
])
```

Stops on the first error.

---

## Apps & System

### App

Launch an application.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | str | *required* | Application name or path |
| `args` | list | None | Command-line arguments |
| `url` | str | None | URL to open (launches default browser if name not set) |

```
App(name="notepad")
App(name="chrome", url="https://example.com")
App(name="code", args=["--new-window", "C:\\project"])
```

Waits up to 5 seconds for app windows to appear and moves them to the agent screen automatically. If windows appear later, use `RecoverWindow`.

---

### PowerShell

Run a PowerShell command.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `command` | str | *required* | PowerShell command to execute |
| `timeout` | int | 30 | Seconds to wait, clamped to [1, 120] |

```
PowerShell(command="Get-Process | Select-Object -First 10")
PowerShell(command="Get-ChildItem C:\\Users", timeout=10)
```

Returns stdout and stderr as text. The command runs in a new PowerShell process (not an interactive session).

---

### FileSystem

File and directory operations.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `action` | str | *required* | `"read"`, `"write"`, `"list"`, `"info"`, `"delete"`, `"copy"`, `"move"` |
| `path` | str | *required* | Target file or directory |
| `content` | str | None | Text content (for `write`) |
| `destination` | str | None | Target path (for `copy` and `move`) |

```
FileSystem(action="read", path="C:\\Users\\me\\notes.txt")
FileSystem(action="write", path="C:\\temp\\out.txt", content="Hello")
FileSystem(action="list", path="C:\\Users\\me\\Documents")
FileSystem(action="copy", path="C:\\a.txt", destination="C:\\b.txt")
```

---

### Clipboard

Read or write clipboard text.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `action` | str | "get" | `"get"` to read, `"set"` to write |
| `content` | str | None | Text to write (required for `set`) |

```
Clipboard()
Clipboard(action="set", content="copied text")
```

---

### Process

List or kill processes.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `action` | str | "list" | `"list"` or `"kill"` |
| `name` | str | None | Filter/target by process name |
| `pid` | int | None | Target by process ID |

```
Process()
Process(action="list", name="chrome")
Process(action="kill", name="notepad")
Process(action="kill", pid=1234)
```

---

### Registry

Read, write, or list Windows registry values.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `action` | str | *required* | `"read"`, `"write"`, `"list"` |
| `key` | str | *required* | Registry path (e.g., `HKCU\Software\MyApp`) |
| `name` | str | None | Value name (for `read`/`write`) |
| `value` | str | None | Data to write |
| `value_type` | str | "REG_SZ" | `REG_SZ`, `REG_DWORD`, `REG_QWORD`, `REG_BINARY`, `REG_EXPAND_SZ`, `REG_MULTI_SZ` |

```
Registry(action="list", key="HKCU\\Software")
Registry(action="read", key="HKCU\\Software\\MyApp", name="Setting")
Registry(action="write", key="HKCU\\Software\\MyApp", name="Setting", value="hello")
```

---

### Notification

Show a Windows toast notification.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `title` | str | *required* | Notification title |
| `message` | str | *required* | Notification body text |

```
Notification(title="Task Complete", message="The report has been generated.")
```

---

### Scrape

Fetch a URL and return its text content.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | str | *required* | URL to fetch |

```
Scrape(url="https://example.com")
```

Returns up to 50,000 characters of text with HTML tags stripped.

---

### InputStatus

Check the current input mode. Takes no parameters.

```
InputStatus()
```

Returns a dict with:
- `mode`: current input mode name
- `agent_can_input`: boolean, whether the agent is allowed to send input
- `description`: human-readable explanation of the current mode
