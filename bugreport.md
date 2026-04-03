# Bug Report: Stdio Transport Hang After VDD Display Creation

**Status:** RESOLVED (2026-04-02)
**Severity:** Critical — blocked all tool calls after display creation via stdio transport
**Affected:** WindowsPC-MCP stdio transport on Windows 11 + Python 3.14

## Symptom

After calling `CreateScreen` (which creates a Parsec VDD virtual display), all subsequent async tool calls (Screenshot, Snapshot) hung indefinitely when using stdio transport. Sync tools (Click, Type, ScreenInfo) continued to work.

## Root Cause

`dxcam` was imported at module level in `display/capture.py`:

```python
try:
    import dxcam    # <-- COM/DXGI initialization happens here
except ImportError:
    dxcam = None

dxcam = None  # disabled anyway, but import already ran
```

When `capture.py` was first imported **inside an async tool handler** (after VDD display creation), `import dxcam` triggered COM/DXGI initialization via `comtypes`. This deadlocked the anyio event loop's ProactorEventLoop (IOCP) on Windows.

The import was deferred because Screenshot's tool function did `from windowspc_mcp.display.capture import capture_region` inside the function body, and no other code imported `capture.py` before the first Screenshot call.

## Why It Only Affected Stdio Transport

- **In-process** (`mcp.call_tool()`): The event loop is a simple `asyncio.run()` without IOCP-based stdin/stdout readers. COM init doesn't conflict.
- **Stdio transport**: FastMCP uses `anyio` + `ProactorEventLoop` with IOCP handles for stdin/stdout. COM/DXGI initialization in this context causes a threading deadlock.

## Investigation Timeline

| Test | Result | What it ruled out |
|------|--------|-------------------|
| Full server via stdio | Screenshot hangs | Confirmed the bug |
| In-process via `mcp.call_tool()` | All tools work | Isolated to stdio transport |
| Inline tools + VDD + guard decorator | All work | Not a FastMCP registration bug |
| `register_all()` + real components | Screenshot hangs | Something in tool modules |
| Only `screenshot.register()` | Screenshot hangs | Isolated to screenshot module |
| Async+guarded tools with no capture | All work | Not about decorators |
| First capture call after VDD | Always hangs | First GDI/import triggers it |
| 60s timeout with server logging | Print before import works, import hangs | Import itself deadlocks |
| Pre-import capture.py at startup | Screenshot works | Confirmed lazy import is the cause |
| Skip dxcam import, use Pillow directly | Screenshot works | Confirmed dxcam import is the trigger |

## Fix

Removed the top-level `import dxcam` from `display/capture.py`. Moved it to a lazy import inside `_capture_dxcam()` (the only function that uses it). Since dxcam is currently disabled (`dxcam = None`), the import never runs during normal operation.

```python
# Before (deadlocks):
try:
    import dxcam        # COM/DXGI init at import time
except ImportError:
    dxcam = None
dxcam = None            # disabled anyway

# After (safe):
dxcam = None            # disabled by default

def _capture_dxcam(...):
    global dxcam
    if dxcam is None:
        import dxcam as _dxcam   # lazy import, only when explicitly enabled
        dxcam = _dxcam
    ...
```

## Verification

- Full server: `CreateScreen` -> `Screenshot` -> `Snapshot` -> `Click` all pass via stdio
- Test suite: 1,348 tests pass (0 failures)

## Lessons

1. **Never import COM/DXGI/Win32 libraries at module level** in code that may be lazily loaded inside async handlers. Always use lazy imports or pre-import at startup.
2. **Disabling a library by setting it to `None` after import doesn't prevent the import side effects** — the module initialization has already run.
3. **Stdio transport on Windows (ProactorEventLoop + IOCP) is sensitive to COM apartment initialization** — operations that are safe in a plain `asyncio.run()` can deadlock when stdin/stdout are managed by IOCP.
