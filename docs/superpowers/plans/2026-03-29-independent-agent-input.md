# Independent Agent Input — Implementation Plan

**Goal:** Give the agent its own mouse and keyboard so it never moves the real cursor, steals focus, or interferes with the user.

**Current problem:** All agent input goes through `SendInput` (global input queue) and `SetCursorPos`/`SetForegroundWindow`. This physically moves the user's cursor and steals their window focus.

---

## Approach: PostMessage + UIA Patterns (Hybrid C)

Replace the global input injection with **window-targeted message delivery**:

- **PostMessageW** sends mouse/keyboard events directly to a specific window's message queue — no cursor movement, no focus theft
- **UIA Patterns** (Invoke, Toggle, SetValue, Scroll) interact with elements programmatically — completely invisible
- **Virtual focus tracking** — the service remembers which HWND the agent last clicked, so keyboard input has a target without needing `SetForegroundWindow`

### Why PostMessage over SendInput?

| | SendInput (current) | PostMessage (new) |
|---|---|---|
| Cursor | Moves real cursor | No effect on cursor |
| Focus | Requires SetForegroundWindow | Sends directly to HWND |
| User interference | Constant | Zero |
| App compatibility | ~99% | ~90% (some apps ignore posted input) |
| Coordinate system | Virtual screen 0-65535 | Client-relative per window |

The ~10% compatibility gap is covered by UIA patterns for labeled elements (buttons, text fields, checkboxes, scrollable areas).

---

## Architecture Changes

### New module: `uia/message_input.py`

Provides low-level PostMessage functions that mirror what `controls.py` does with SendInput:

- **Window targeting** — `WindowFromPoint` → `ChildWindowFromPointEx` recursion to find the deepest child window at a coordinate. This replaces the `enumerate_windows` + hit-test loop.
- **Mouse** — Post `WM_LBUTTONDOWN`/`WM_LBUTTONUP` (and right/middle variants) with client-relative coords packed into LPARAM. Requires `ScreenToClient` conversion.
- **Keyboard** — Post `WM_CHAR` for text characters, `WM_KEYDOWN`/`WM_KEYUP` for special keys (with proper scan codes via `MapVirtualKeyW`).
- **Scroll** — Post `WM_MOUSEWHEEL`/`WM_MOUSEHWHEEL` with delta in WPARAM high word and screen coords in LPARAM.
- **Mouse move** — Post `WM_MOUSEMOVE` for hover/drag operations.

### Modified: `uia/patterns.py`

Add two new pattern helpers alongside existing `try_invoke` and `try_set_value`:

- **`try_toggle`** — TogglePattern (ID 10015) for checkboxes
- **`try_scroll`** — ScrollPattern (ID 10004) with SmallIncrement/SmallDecrement mapped from wheel detent amounts

### Rewritten: `input/service.py`

The `AgentInputService` class changes from "focus then SendInput" to "PostMessage to target HWND":

**Key design decisions:**

1. **Virtual focus via `_active_hwnd`** — Tracks which window the agent last clicked. Keyboard operations target this HWND. No system focus change needed.

2. **`_resolve_hwnd(abs_x, abs_y)`** replaces `_ensure_focus` — Uses `find_target_hwnd` (fast `WindowFromPoint` call) instead of enumerate+hit-test. Updates `_active_hwnd` as side effect.

3. **`_find_agent_window()`** as fallback — When no click has happened yet and a shortcut or type needs a target, scan for the topmost visible window on the agent screen. Same logic as old `_find_foreground_on_agent_screen` but used only as last resort.

4. **All `send_input()` calls become `post_key_event()` calls** — For caret positioning (Home/End), clear (Ctrl+A, Backspace), enter, and shortcuts. Each key event goes to the specific HWND.

5. **Drag uses PostMessage sequence** — `WM_LBUTTONDOWN` → `WM_MOUSEMOVE` → `WM_LBUTTONUP` on the target HWND instead of SendInput mouse events.

### Modified: `tools/multi.py`

`multi_edit` currently imports `click_at`/`type_text` from controls directly, bypassing the service. Change it to use `svc.click()` and `svc.type_text()` so it also goes through PostMessage.

### Modified: `uia/core.py`

Add `argtypes`/`restype` declarations for the new Win32 functions: `PostMessageW`, `WindowFromPoint`, `ChildWindowFromPointEx`, `ScreenToClient`, `MapVirtualKeyW`.

### Unchanged

- **Confinement engine** — Still validates agent-relative coords and translates to absolute. PostMessage functions receive the same absolute coords.
- **Tool layer** (`tools/input.py`) — Same public API, same label resolution, same confinement validation. Only the service underneath changes.
- **TreeService** — No changes. Snapshot/label resolution works the same.
- **`uia/controls.py`** — Kept as-is. Window helper functions (`get_window_rect`, `enumerate_windows`, etc.) are still used. The SendInput input functions (`click_at`, `type_text`, `scroll_at`, `move_cursor`) become unused by the service but stay available as legacy.

---

## Task Breakdown

### Task 1: Win32 argtypes in core.py
Add argtypes for the 5 new Win32 functions. Pure declaration, no behavior change. Run existing tests to verify no regression.

### Task 2: Create message_input.py + tests
Build the PostMessage input layer. Test each function with mocked `user32` calls. This is the largest new file (~120 lines).

### Task 3: Add try_toggle + try_scroll to patterns.py + tests
Two new UIA pattern helpers following the exact same structure as existing `try_invoke`/`try_set_value`.

### Task 4: Export new symbols from uia/__init__.py
Wire up the new module and pattern helpers in the package exports.

### Task 5: Rewrite AgentInputService + tests
The core behavior change. Replace all SendInput usage with PostMessage calls. Add `_active_hwnd` tracking. Remove `_ensure_focus`. Update all service tests to mock the new functions.

### Task 6: Fix multi_edit to use service
Two-line change: use `svc.click()` and `svc.type_text()` instead of raw imports.

### Task 7: Full test suite verification
Run all ~1028 tests. Fix any e2e tests that mock old import paths.

### Task 8: Verify no SendInput leaks
Grep the input service to confirm zero references to `SendInput`, `SetCursorPos`, or `SetForegroundWindow`.

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Some apps ignore PostMessage mouse events (WPF, Electron, DirectX) | UIA patterns handle labeled elements; agent screen runs standard desktop apps |
| WM_CHAR doesn't handle IME/complex input | Same limitation as current Unicode SendInput; sufficient for English text |
| Virtual focus gets stale if user moves windows | `_resolve_hwnd` re-queries on every coordinate-based action |
| ChildWindowFromPointEx misses layered/transparent windows | CWP_SKIPINVISIBLE flag; transparent windows are rare on agent display |
