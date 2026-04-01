# GhostCursorOverlay + ConflictDetector — `desktop/overlay.py`

Visual feedback and conflict prevention for COWORK mode.

## GhostCursorOverlay

A 32x32 pixel window that shows the agent's cursor position on the user's desktop.

### Window Properties

```text
Style:    WS_EX_LAYERED      — supports transparency
        | WS_EX_TRANSPARENT   — click-through (input passes to windows below)
        | WS_EX_TOPMOST       — always on top
        | WS_EX_TOOLWINDOW    — doesn't appear in taskbar
        | WS_POPUP            — no frame/border
```

### Visual States

```python
class CursorState(Enum):
    WORKING  # Blue  (0x00FF0000 BGR) — agent actively executing
    WAITING  # Gray  (0x00808080)     — agent waiting for gap
    HIDDEN   # Not visible            — no pending work
```

Transparency: magenta color key (0x00FF00FF) via `SetLayeredWindowAttributes`. The window background is magenta (transparent), cursor area is filled with state color via GDI `FillRect`.

### Public API

```python
class GhostCursorOverlay:
    CURSOR_SIZE = 32

    def create(self) -> None       # RegisterClassW + CreateWindowExW
    def move_to(self, x, y)        # SetWindowPos with HWND_TOPMOST, SWP_NOACTIVATE
    def set_state(self, state)     # ShowWindow(SW_HIDE or SW_SHOWNOACTIVATE) + color fill
    def destroy(self) -> None      # DestroyWindow + UnregisterClassW (idempotent)

    @property position -> (x, y)
    @property state -> CursorState
```

## ConflictDetector

Prevents the agent from interacting with the same window the human is using.

### How It Works

```text
agent wants to click at (100, 200)
        │
        ▼
GetCursorPos() → human cursor at (500, 300)
WindowFromPoint(500, 300) → human_hwnd
WindowFromPoint(100, 200) → agent_hwnd
        │
        ▼
human_hwnd == agent_hwnd?
    YES → conflict! return window title
    NO  → no conflict, return None
```

### Public API

```python
class ConflictDetector:
    def check_conflict(self, agent_target_x, agent_target_y) -> str | None
        # Returns None (safe) or window title (conflict)
        # Handles GetCursorPos failure gracefully (returns None)

    def get_human_window(self) -> int | None
        # Returns HWND under human cursor, or None
```

### Edge Cases

- `GetCursorPos` fails → returns None (no conflict assumed)
- `WindowFromPoint` returns NULL for either position → no conflict
- Empty window title → returns `"<untitled>"` on conflict
