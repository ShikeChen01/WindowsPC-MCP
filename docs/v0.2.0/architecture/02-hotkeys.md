# HotkeyService — `desktop/hotkeys.py`

System-wide hotkey registration and dispatch. Runs a Win32 message pump in a daemon thread to catch `WM_HOTKEY` messages.

## Hotkey Bindings

| Hotkey | HotkeyId | Action |
|--------|----------|--------|
| Ctrl+Alt+Space | TOGGLE (1) | Cycle modes |
| Ctrl+Alt+Enter | OVERRIDE (2) | Instant HUMAN_OVERRIDE |
| Ctrl+Alt+S | EMERGENCY (3) | Emergency stop |

## Public API

```python
class HotkeyId(IntEnum):
    TOGGLE = 1
    OVERRIDE = 2
    EMERGENCY = 3

class HotkeyService:
    def start(self, callbacks: dict[HotkeyId, Callable[[], None]]) -> None
        # 1. Spawns daemon thread running _listener_main()
        # 2. Thread creates hidden HWND_MESSAGE window
        # 3. Registers all 3 hotkeys on that window
        # 4. Enters GetMessageW loop
        # Raises InvalidStateError if already running
        # Raises HotkeyError if thread doesn't become ready in 5s

    def stop(self) -> None
        # Posts WM_QUIT to listener thread
        # Joins thread (5s timeout)
        # Idempotent

    @property
    def is_running(self) -> bool
```

## How It Works

```
start() ──► spawn daemon thread
                │
                ▼
        RegisterClassW("WindowsPC_MCP_Hotkey")
        CreateWindowExW(HWND_MESSAGE parent)
        RegisterHotKey × 3
        _ready.set()  ──► start() returns
                │
                ▼
        GetMessageW loop:
            WM_HOTKEY → _dispatch_hotkey(wParam)
                            → invoke callback
            WM_QUIT   → break
                │
                ▼
        _cleanup():
            UnregisterHotKey × 3
            DestroyWindow
            UnregisterClassW
```

## Callback Safety

- Callbacks run in the listener thread, not the caller's thread
- Callback exceptions are caught and logged — never crash the listener
- Unknown hotkey IDs are logged as debug, not errors

## Resilience

- `RegisterClassW` failure with `ERROR_CLASS_ALREADY_EXISTS` (1410) is tolerated — handles process crash without cleanup
- `_ready.wait(timeout=5.0)` raises `HotkeyError` on timeout
- WNDPROC callback stored as `self._wndproc_ref` to prevent GC (ctypes pitfall)

## Error: `HotkeyError(WindowsMCPError)`

Raised when RegisterHotKey, CreateWindowExW, or RegisterClassW fails, or when the listener thread doesn't become ready in time.
