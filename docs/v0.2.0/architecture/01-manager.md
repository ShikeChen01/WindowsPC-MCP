# DesktopManager — `desktop/manager.py`

Win32 desktop lifecycle management. Creates an isolated desktop for the agent with its own cursor, focus chain, and window set.

## What a Win32 Desktop Is

A desktop is a kernel object under a window station. Each desktop has:
- Independent cursor position and state
- Independent focus chain (which window is active)
- Independent keyboard state
- Its own set of visible windows

Shared with user's desktop: filesystem, registry, processes, RAM, CPU, network.

## Public API

```python
class DesktopManager:
    def __init__(self)
        # Captures user's current desktop handle via GetThreadDesktop(GetCurrentThreadId())

    def create_agent_desktop(self) -> None
        # CreateDesktopW("WindowsPC_MCP_Agent", DESKTOP_ALL_ACCESS)
        # Raises InvalidStateError if already exists

    def switch_to_agent(self) -> None
        # SwitchDesktop(agent_handle) — makes agent desktop the input desktop
        # No-op if already on agent desktop

    def switch_to_user(self) -> None
        # SwitchDesktop(user_handle) — restores user's desktop
        # No-op if already on user desktop

    def launch_on_agent(self, executable, args=None, cwd=None) -> int
        # subprocess.Popen with STARTUPINFO.lpDesktop = "WindowsPC_MCP_Agent"
        # Stores Popen in self._processes for later cleanup
        # Returns PID

    def destroy(self) -> None
        # Terminates all tracked processes (terminate → kill fallback)
        # Switches to user desktop if needed
        # CloseDesktop(agent_handle)
        # Idempotent

    # Context manager: __enter__ returns self, __exit__ calls destroy()
```

## Win32 Bindings

All use `ctypes.WinDLL("user32", use_last_error=True)`. Error codes via `ctypes.get_last_error()`.

| Function | Purpose |
|----------|---------|
| `CreateDesktopW` | Create new desktop |
| `SwitchDesktop` | Change input desktop |
| `CloseDesktop` | Destroy desktop handle |
| `GetThreadDesktop` | Get current thread's desktop |
| `OpenInputDesktop` | Get current input desktop (bound, unused) |
| `SetThreadDesktop` | Set thread's desktop (bound, unused) |

## Thread Safety

`threading.Lock` serializes all public methods. Internal `_switch_to_user_unlocked()` exists for use by `destroy()` which already holds the lock.

## Process Tracking

`launch_on_agent()` stores Popen objects in `self._processes`. On `destroy()`, all running processes are terminated (with 3s timeout, then killed). This supports emergency stop cleanup.

## Error: `DesktopError(WindowsMCPError)`

Raised when Win32 desktop operations fail (CreateDesktopW returns NULL, SwitchDesktop returns FALSE).
