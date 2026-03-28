# WindowsMCP Custom Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a purpose-built MCP server that confines AI agent GUI interaction to a virtual display, with a floating toolbar and interactive viewer for monitoring.

**Architecture:** Three-process system — Confined MCP Server (FastMCP/Python), Management UI (PyQt6), and Parsec VDD virtual display driver. The confinement engine validates every GUI write action against the agent's screen bounds before execution. Tools use UIA patterns preferred over SendInput for reliability.

**Tech Stack:** Python 3.12+, FastMCP, comtypes, pywin32, dxcam/mss/Pillow, ctypes (Parsec VDD), PyQt6, uv

**Spec:** `docs/superpowers/specs/2026-03-28-windowsmcp-custom-design.md`

**Driver choice update:** Parsec VDD instead of IddSampleDriver — signed driver, simplest IOCTL interface (4 codes), reliable keep-alive mechanism.

---

## File Structure

```
WindowsMCP_Custom/
├── src/
│   └── windowsmcp_custom/
│       ├── __init__.py
│       ├── __main__.py              # Entry point, FastMCP server, CLI
│       ├── server.py                # Server state machine, lifespan
│       ├── confinement/
│       │   ├── __init__.py
│       │   ├── engine.py            # Confinement engine — classify, validate, translate
│       │   ├── shortcuts.py         # Shortcut allowlist/blocklist
│       │   └── bounds.py            # Screen bounds tracking, WM_DISPLAYCHANGE
│       ├── display/
│       │   ├── __init__.py
│       │   ├── driver.py            # Parsec VDD ctypes wrapper
│       │   ├── manager.py           # Virtual display lifecycle
│       │   ├── identity.py          # Display state file persistence
│       │   └── capture.py           # Screenshot capture (dxcam/mss/pillow)
│       ├── tools/
│       │   ├── __init__.py          # register_all()
│       │   ├── screen.py            # CreateScreen, DestroyScreen, ScreenInfo, RecoverWindow
│       │   ├── screenshot.py        # Screenshot, Snapshot
│       │   ├── input.py             # Click, Type, Move, Scroll, Shortcut, Wait
│       │   ├── multi.py             # MultiSelect, MultiEdit
│       │   ├── app.py               # App launch + window shepherd
│       │   ├── shell.py             # PowerShell
│       │   ├── filesystem.py        # FileSystem
│       │   ├── clipboard.py         # Clipboard
│       │   ├── process.py           # Process
│       │   ├── registry.py          # Registry
│       │   ├── notification.py      # Notification
│       │   └── scrape.py            # Scrape
│       ├── uia/
│       │   ├── __init__.py
│       │   ├── core.py              # UIAutomation COM singleton
│       │   ├── controls.py          # Control wrappers
│       │   └── patterns.py          # UIA patterns
│       └── ipc/
│           ├── __init__.py
│           ├── status.py            # Named pipe status publisher
│           ├── frames.py            # Shared memory frame buffer
│           └── commands.py          # Named pipe command receiver
├── ui/
│   ├── __init__.py
│   ├── main.py                      # UI process entry point
│   ├── toolbar.py                   # Floating toolbar widget
│   └── viewer.py                    # Interactive viewer window
├── tests/
│   ├── __init__.py
│   ├── test_confinement.py
│   ├── test_display_manager.py
│   ├── test_driver.py
│   ├── test_tools_screen.py
│   ├── test_tools_input.py
│   ├── test_tools_passthrough.py
│   ├── test_capture.py
│   ├── test_state_machine.py
│   └── conftest.py                  # Shared fixtures
├── docs/
├── pyproject.toml
└── README.md
```

---

## Dependency Graph

```
Task 1 (Scaffolding)
  ├── Task 2 (UIA Wrapper)
  │     └── Task 8 (Input Tools) ──────────────┐
  │     └── Task 10 (App Tool) ────────────────┤
  │     └── Task 12 (Multi Tools) ─────────────┤
  ├── Task 3 (Parsec VDD Driver)               │
  │     └── Task 4 (Display Manager) ──────────┤
  │           └── Task 5 (Confinement Engine)   │
  │                 ├── Task 6 (Shortcut Filter)│
  │                 ├── Task 7 (Screen Tools) ──┤
  │                 ├── Task 9 (Screenshot) ────┤
  │                 └── Task 8, 10, 12 ─────────┤
  ├── Task 11 (Pass-through Tools) ─────────────┤
  └── Task 13 (State Machine) ─────────────────┤
                                                │
                                    Task 14 (Tool Registry + Server Integration)
                                                │
                              ┌─────────────────┤
                              │                 │
                    Task 15 (IPC)    Task 17 (E2E with Claude Code)
                              │
                    Task 16 (Management UI)
```

**Parallel opportunities:** Tasks 2, 3 can run in parallel. Tasks 8, 9, 10, 11, 12 can run in parallel once Task 5 is complete. Tasks 15-16 can run in parallel with Task 17.

---

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/windowsmcp_custom/__init__.py`
- Create: `src/windowsmcp_custom/__main__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "windowsmcp-custom"
version = "0.1.0"
description = "Confined Windows MCP server with virtual display isolation for AI agents."
requires-python = ">=3.12"
dependencies = [
    "click>=8.2.0",
    "comtypes>=1.4.15",
    "dxcam>=0.3.0",
    "fastmcp>=3.0",
    "mss>=9.0.0",
    "pillow>=11.0.0",
    "psutil>=7.0.0",
    "pywin32>=311",
    "thefuzz>=0.22.1",
]

[project.optional-dependencies]
ui = ["PyQt6>=6.6.0"]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "ruff>=0.9.0",
]

[project.scripts]
windowsmcp-custom = "windowsmcp_custom.__main__:main"

[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create package init**

Create `src/windowsmcp_custom/__init__.py`:
```python
"""WindowsMCP Custom — Confined agent desktop MCP server."""
```

- [ ] **Step 3: Create minimal entry point**

Create `src/windowsmcp_custom/__main__.py`:
```python
"""Entry point for the WindowsMCP Custom server."""

import click
from fastmcp import FastMCP
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastMCP):
    """Initialize and clean up server components."""
    yield


mcp = FastMCP(
    name="windowsmcp-custom",
    instructions=(
        "WindowsMCP Custom provides tools to interact with a confined virtual display. "
        "The agent operates on a dedicated virtual screen and cannot interact with the "
        "user's physical screens. Use CreateScreen to set up the agent display first."
    ),
    lifespan=lifespan,
)


@click.command()
@click.option("--transport", type=click.Choice(["stdio", "sse"]), default="stdio")
@click.option("--host", default="localhost", type=str)
@click.option("--port", default=8000, type=int)
def main(transport: str, host: str, port: int):
    """Start the WindowsMCP Custom server."""
    mcp.run(transport=transport, host=host, port=port, show_banner=False)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Create test infrastructure**

Create `tests/__init__.py` (empty).

Create `tests/conftest.py`:
```python
"""Shared test fixtures for WindowsMCP Custom."""

import pytest
from dataclasses import dataclass


@dataclass
class MockBounds:
    """Mock screen bounds for testing without a real virtual display."""
    x: int = 3840
    y: int = 0
    width: int = 1920
    height: int = 1080

    @property
    def left(self) -> int:
        return self.x

    @property
    def top(self) -> int:
        return self.y

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height


@pytest.fixture
def agent_bounds():
    """Default agent screen bounds for tests."""
    return MockBounds()


@pytest.fixture
def user_bounds():
    """Default user screen bounds for tests."""
    return MockBounds(x=0, y=0, width=1920, height=1080)
```

- [ ] **Step 5: Install and verify**

```bash
cd C:/Users/doubi/Claude_Project/WindowsMCP_Custom
uv venv
uv pip install -e ".[dev]"
uv run python -c "from windowsmcp_custom.__main__ import mcp; print(f'Server: {mcp.name}')"
```

Expected: `Server: windowsmcp-custom`

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/ tests/
git commit -m "feat: project scaffolding with FastMCP entry point"
```

---

### Task 2: UIA Wrapper Module

**Files:**
- Create: `src/windowsmcp_custom/uia/__init__.py`
- Create: `src/windowsmcp_custom/uia/core.py`
- Create: `src/windowsmcp_custom/uia/controls.py`
- Create: `src/windowsmcp_custom/uia/patterns.py`

This is adapted from the existing Windows MCP UIA module. The wrapper provides the COM automation client singleton and helper functions for element discovery, input injection, and pattern access.

- [ ] **Step 1: Create UIA core with COM singleton**

Create `src/windowsmcp_custom/uia/core.py`:
```python
"""UIAutomation COM client singleton."""

import ctypes
import ctypes.wintypes as wintypes
import logging

logger = logging.getLogger(__name__)

# Set return types for Win32 APIs we use
ctypes.windll.user32.GetForegroundWindow.restype = ctypes.c_void_p
ctypes.windll.user32.GetAncestor.restype = ctypes.c_void_p
ctypes.windll.user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
ctypes.windll.user32.SetForegroundWindow.restype = wintypes.BOOL
ctypes.windll.user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
ctypes.windll.user32.SetCursorPos.restype = wintypes.BOOL
ctypes.windll.user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
ctypes.windll.user32.GetCursorPos.restype = wintypes.BOOL
ctypes.windll.user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.RECT)]
ctypes.windll.user32.GetWindowRect.restype = wintypes.BOOL
ctypes.windll.user32.MoveWindow.argtypes = [
    ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.BOOL,
]
ctypes.windll.user32.MoveWindow.restype = wintypes.BOOL
ctypes.windll.user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
ctypes.windll.user32.IsWindowVisible.restype = wintypes.BOOL
ctypes.windll.user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
ctypes.windll.user32.GetWindowThreadProcessId.restype = wintypes.DWORD
ctypes.windll.user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
ctypes.windll.user32.ShowWindow.restype = wintypes.BOOL
ctypes.windll.user32.EnumWindows.restype = wintypes.BOOL
ctypes.windll.user32.GetClassNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
ctypes.windll.user32.GetClassNameW.restype = ctypes.c_int
ctypes.windll.user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
ctypes.windll.user32.GetWindowTextW.restype = ctypes.c_int
ctypes.windll.user32.GetWindowTextLengthW.argtypes = [ctypes.c_void_p]
ctypes.windll.user32.GetWindowTextLengthW.restype = ctypes.c_int

# SendInput structures
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_ABSOLUTE = 0x8000
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_KEYUP = 0x0002
SW_RESTORE = 9
GA_ROOT = 2


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]


def send_input(*inputs: INPUT):
    """Send input events via SendInput API."""
    n = len(inputs)
    arr = (INPUT * n)(*inputs)
    ctypes.windll.user32.SendInput(n, arr, ctypes.sizeof(INPUT))


class _AutomationClient:
    """Singleton UIAutomation COM client."""

    _instance = None

    @classmethod
    def instance(cls) -> "_AutomationClient":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        try:
            ctypes.windll.ole32.CoInitialize(None)
        except Exception:
            pass

        import comtypes.client

        for attempt in range(3):
            try:
                self.UIAutomationCore = comtypes.client.GetModule("UIAutomationCore.dll")
                self.IUIAutomation = comtypes.client.CreateObject(
                    "{ff48dba4-60ef-4201-aa87-54103eef594e}",
                    interface=self.UIAutomationCore.IUIAutomation,
                )
                self.ViewWalker = self.IUIAutomation.RawViewWalker
                break
            except Exception as ex:
                if attempt == 2:
                    raise ex
                logger.warning(f"UIA init attempt {attempt + 1} failed, retrying...")
```

- [ ] **Step 2: Create controls module**

Create `src/windowsmcp_custom/uia/controls.py`:
```python
"""Window and element control helpers."""

import ctypes
import ctypes.wintypes as wintypes
import logging
from windowsmcp_custom.uia.core import (
    GA_ROOT, SW_RESTORE, _AutomationClient,
    INPUT, INPUT_UNION, MOUSEINPUT, KEYBDINPUT, INPUT_MOUSE, INPUT_KEYBOARD,
    MOUSEEVENTF_MOVE, MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP,
    MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP, MOUSEEVENTF_MIDDLEDOWN,
    MOUSEEVENTF_MIDDLEUP, MOUSEEVENTF_WHEEL, MOUSEEVENTF_ABSOLUTE,
    KEYEVENTF_UNICODE, KEYEVENTF_KEYUP, send_input,
)

logger = logging.getLogger(__name__)
user32 = ctypes.windll.user32


def get_foreground_window() -> int:
    """Get handle of the current foreground window."""
    return user32.GetForegroundWindow() or 0


def set_foreground_window(hwnd: int) -> bool:
    """Attempt to bring a window to the foreground."""
    if not hwnd:
        return False
    # Restore if minimized
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    # Try AttachThreadInput trick for more reliable activation
    current_thread = ctypes.windll.kernel32.GetCurrentThreadId()
    target_thread = user32.GetWindowThreadProcessId(hwnd, None)
    if current_thread != target_thread:
        user32.AttachThreadInput(current_thread, target_thread, True)
    result = user32.SetForegroundWindow(hwnd)
    if current_thread != target_thread:
        user32.AttachThreadInput(current_thread, target_thread, False)
    return bool(result)


def get_window_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    """Get window rect as (left, top, right, bottom)."""
    rect = wintypes.RECT()
    if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return (rect.left, rect.top, rect.right, rect.bottom)
    return None


def move_window(hwnd: int, x: int, y: int, w: int, h: int):
    """Move and resize a window."""
    user32.MoveWindow(hwnd, x, y, w, h, True)


def get_window_title(hwnd: int) -> str:
    """Get the title text of a window."""
    length = user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def get_window_class(hwnd: int) -> str:
    """Get the class name of a window."""
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def get_window_pid(hwnd: int) -> int:
    """Get the process ID of a window."""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def get_root_window(hwnd: int) -> int:
    """Get the root owner window."""
    return user32.GetAncestor(hwnd, GA_ROOT) or hwnd


def is_window_visible(hwnd: int) -> bool:
    """Check if a window is visible."""
    return bool(user32.IsWindowVisible(hwnd))


def enumerate_windows() -> list[int]:
    """Get all top-level window handles."""
    handles = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, ctypes.c_void_p, wintypes.LPARAM)

    def callback(hwnd, lparam):
        handles.append(hwnd)
        return True

    user32.EnumWindows(WNDENUMPROC(callback), 0)
    return handles


def click_at(x: int, y: int, button: str = "left", clicks: int = 1):
    """Send mouse click at absolute screen coordinates."""
    # Normalize to 0-65535 range for SendInput absolute coords
    screen_w = user32.GetSystemMetrics(0)  # SM_CXSCREEN (virtual screen width)
    screen_h = user32.GetSystemMetrics(1)  # SM_CYSCREEN
    # Use virtual screen metrics for multi-monitor
    vscreen_x = user32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
    vscreen_y = user32.GetSystemMetrics(77)  # SM_YVIRTUALSCREEN
    vscreen_w = user32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
    vscreen_h = user32.GetSystemMetrics(79)  # SM_CYVIRTUALSCREEN

    abs_x = int((x - vscreen_x) * 65535 / vscreen_w)
    abs_y = int((y - vscreen_y) * 65535 / vscreen_h)

    down_flag, up_flag = {
        "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
        "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
        "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
    }.get(button, (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP))

    # Move to position
    move = INPUT(type=INPUT_MOUSE, union=INPUT_UNION(
        mi=MOUSEINPUT(dx=abs_x, dy=abs_y, dwFlags=MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE)
    ))
    send_input(move)

    # Click
    for _ in range(clicks):
        down = INPUT(type=INPUT_MOUSE, union=INPUT_UNION(
            mi=MOUSEINPUT(dx=abs_x, dy=abs_y, dwFlags=down_flag | MOUSEEVENTF_ABSOLUTE)
        ))
        up = INPUT(type=INPUT_MOUSE, union=INPUT_UNION(
            mi=MOUSEINPUT(dx=abs_x, dy=abs_y, dwFlags=up_flag | MOUSEEVENTF_ABSOLUTE)
        ))
        send_input(down, up)


def type_text(text: str):
    """Type text using Unicode SendInput."""
    for char in text:
        code = ord(char)
        down = INPUT(type=INPUT_KEYBOARD, union=INPUT_UNION(
            ki=KEYBDINPUT(wScan=code, dwFlags=KEYEVENTF_UNICODE)
        ))
        up = INPUT(type=INPUT_KEYBOARD, union=INPUT_UNION(
            ki=KEYBDINPUT(wScan=code, dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)
        ))
        send_input(down, up)


def scroll_at(x: int, y: int, amount: int, horizontal: bool = False):
    """Scroll at absolute coordinates. amount > 0 = up/right, < 0 = down/left."""
    user32.SetCursorPos(x, y)
    if horizontal:
        # WM_MOUSEHWHEEL uses 0x01000
        flag = 0x01000
    else:
        flag = MOUSEEVENTF_WHEEL
    scroll = INPUT(type=INPUT_MOUSE, union=INPUT_UNION(
        mi=MOUSEINPUT(mouseData=amount * 120, dwFlags=flag)
    ))
    send_input(scroll)


def move_cursor(x: int, y: int):
    """Move cursor to absolute screen coordinates."""
    user32.SetCursorPos(x, y)
```

- [ ] **Step 3: Create patterns module**

Create `src/windowsmcp_custom/uia/patterns.py`:
```python
"""UIAutomation pattern helpers for element interaction."""

import logging
from windowsmcp_custom.uia.core import _AutomationClient

logger = logging.getLogger(__name__)


def get_element_from_point(x: int, y: int):
    """Get UIAutomation element at screen coordinates."""
    try:
        client = _AutomationClient.instance()
        from comtypes.gen.UIAutomationClient import tagPOINT
        point = tagPOINT(x, y)
        return client.IUIAutomation.ElementFromPoint(point)
    except Exception:
        logger.debug(f"No UIA element at ({x}, {y})")
        return None


def get_element_from_handle(hwnd: int):
    """Get UIAutomation element from a window handle."""
    try:
        client = _AutomationClient.instance()
        return client.IUIAutomation.ElementFromHandle(hwnd)
    except Exception:
        logger.debug(f"No UIA element for hwnd {hwnd}")
        return None


def get_element_rect(element) -> tuple[int, int, int, int] | None:
    """Get element bounding rect as (left, top, right, bottom)."""
    try:
        rect = element.CurrentBoundingRectangle
        return (rect.left, rect.top, rect.right, rect.bottom)
    except Exception:
        return None


def try_invoke(element) -> bool:
    """Try to invoke an element via InvokePattern."""
    try:
        from comtypes.gen.UIAutomationClient import IUIAutomationInvokePattern
        pattern = element.GetCurrentPattern(10000)  # UIA_InvokePatternId
        if pattern:
            invoke = pattern.QueryInterface(IUIAutomationInvokePattern)
            invoke.Invoke()
            return True
    except Exception:
        pass
    return False


def try_set_value(element, value: str) -> bool:
    """Try to set value via ValuePattern."""
    try:
        from comtypes.gen.UIAutomationClient import IUIAutomationValuePattern
        pattern = element.GetCurrentPattern(10002)  # UIA_ValuePatternId
        if pattern:
            val = pattern.QueryInterface(IUIAutomationValuePattern)
            val.SetValue(value)
            return True
    except Exception:
        pass
    return False
```

- [ ] **Step 4: Create UIA package init**

Create `src/windowsmcp_custom/uia/__init__.py`:
```python
"""UIAutomation wrapper for Windows desktop interaction."""

from windowsmcp_custom.uia.core import _AutomationClient, send_input
from windowsmcp_custom.uia.controls import (
    get_foreground_window, set_foreground_window,
    get_window_rect, move_window, get_window_title,
    get_window_class, get_window_pid, get_root_window,
    is_window_visible, enumerate_windows,
    click_at, type_text, scroll_at, move_cursor,
)
from windowsmcp_custom.uia.patterns import (
    get_element_from_point, get_element_from_handle,
    get_element_rect, try_invoke, try_set_value,
)
```

- [ ] **Step 5: Commit**

```bash
git add src/windowsmcp_custom/uia/
git commit -m "feat: UIA wrapper module — COM client, controls, patterns"
```

---

### Task 3: Parsec VDD Driver Wrapper

**Files:**
- Create: `src/windowsmcp_custom/display/__init__.py`
- Create: `src/windowsmcp_custom/display/driver.py`
- Create: `tests/test_driver.py`

- [ ] **Step 1: Write tests for the driver wrapper**

Create `tests/test_driver.py`:
```python
"""Tests for Parsec VDD driver wrapper.

NOTE: Tests that actually create virtual displays require the Parsec VDD
driver to be installed. They are marked with @pytest.mark.hardware.
Unit tests mock the Win32 APIs.
"""

import pytest
from unittest.mock import patch, MagicMock
from windowsmcp_custom.display.driver import (
    ParsecVDD, VDD_IOCTL_ADD, VDD_IOCTL_REMOVE, VDD_IOCTL_UPDATE, VDD_IOCTL_VERSION,
    open_device_handle,
)


class TestParseVDDConstants:
    def test_ioctl_codes(self):
        assert VDD_IOCTL_ADD == 0x0022e004
        assert VDD_IOCTL_REMOVE == 0x0022a008
        assert VDD_IOCTL_UPDATE == 0x0022a00c
        assert VDD_IOCTL_VERSION == 0x0022e010


class TestParseVDDOpenHandle:
    @patch("windowsmcp_custom.display.driver.SetupDiGetClassDevsA")
    def test_raises_when_driver_not_found(self, mock_setup):
        mock_setup.return_value = -1  # INVALID_HANDLE_VALUE
        with pytest.raises(OSError, match="Could not find Parsec VDD"):
            open_device_handle()


class TestParseVDDLifecycle:
    @patch("windowsmcp_custom.display.driver.open_device_handle")
    def test_context_manager_opens_and_closes(self, mock_open):
        mock_handle = MagicMock()
        mock_open.return_value = mock_handle

        with patch("windowsmcp_custom.display.driver.vdd_update"):
            with patch("windowsmcp_custom.display.driver.CloseHandle") as mock_close:
                vdd = ParsecVDD()
                vdd.close()
                mock_close.assert_called_once_with(mock_handle)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_driver.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'windowsmcp_custom.display'`

- [ ] **Step 3: Implement Parsec VDD driver wrapper**

Create `src/windowsmcp_custom/display/__init__.py`:
```python
"""Virtual display management."""
```

Create `src/windowsmcp_custom/display/driver.py`:
```python
"""Parsec VDD virtual display driver wrapper using ctypes.

Requires Parsec VDD driver installed (signed driver from Parsec installer).
Controls virtual displays via DeviceIoControl with 4 IOCTL codes:
- VDD_IOCTL_ADD: Create a virtual display
- VDD_IOCTL_REMOVE: Remove a virtual display by index
- VDD_IOCTL_UPDATE: Keep-alive ping (must call every <100ms)
- VDD_IOCTL_VERSION: Query driver version
"""

import ctypes
import ctypes.wintypes as wintypes
import logging
import threading
import time
from ctypes import byref, sizeof

logger = logging.getLogger(__name__)

# IOCTL codes for Parsec VDD
VDD_IOCTL_ADD = 0x0022E004
VDD_IOCTL_REMOVE = 0x0022A008
VDD_IOCTL_UPDATE = 0x0022A00C
VDD_IOCTL_VERSION = 0x0022E010

# Win32 constants
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x00000080
FILE_FLAG_NO_BUFFERING = 0x20000000
FILE_FLAG_OVERLAPPED = 0x40000000
FILE_FLAG_WRITE_THROUGH = 0x80000000
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
DIGCF_PRESENT = 0x02
DIGCF_DEVICEINTERFACE = 0x10


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]


# Parsec VDD adapter interface GUID: {00b41627-04c4-429e-a26e-0265cf50c8fa}
VDD_ADAPTER_GUID = GUID(
    0x00B41627, 0x04C4, 0x429E,
    (wintypes.BYTE * 8)(0xA2, 0x6E, 0x02, 0x65, 0xCF, 0x50, 0xC8, 0xFA),
)


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("InterfaceClassGuid", GUID),
        ("Flags", wintypes.DWORD),
        ("Reserved", ctypes.POINTER(ctypes.c_ulong)),
    ]


class SP_DEVICE_INTERFACE_DETAIL_DATA_A(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("DevicePath", ctypes.c_char * 256),
    ]


class OVERLAPPED(ctypes.Structure):
    _fields_ = [
        ("Internal", ctypes.POINTER(ctypes.c_ulong)),
        ("InternalHigh", ctypes.POINTER(ctypes.c_ulong)),
        ("Offset", wintypes.DWORD),
        ("OffsetHigh", wintypes.DWORD),
        ("hEvent", wintypes.HANDLE),
    ]


# Win32 API bindings
setupapi = ctypes.windll.setupapi
kernel32 = ctypes.windll.kernel32

SetupDiGetClassDevsA = setupapi.SetupDiGetClassDevsA
SetupDiGetClassDevsA.restype = wintypes.HANDLE

SetupDiEnumDeviceInterfaces = setupapi.SetupDiEnumDeviceInterfaces
SetupDiEnumDeviceInterfaces.restype = wintypes.BOOL

SetupDiGetDeviceInterfaceDetailA = setupapi.SetupDiGetDeviceInterfaceDetailA
SetupDiGetDeviceInterfaceDetailA.restype = wintypes.BOOL

SetupDiDestroyDeviceInfoList = setupapi.SetupDiDestroyDeviceInfoList
SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL

CreateFileA = kernel32.CreateFileA
CreateFileA.restype = wintypes.HANDLE

DeviceIoControl = kernel32.DeviceIoControl
DeviceIoControl.restype = wintypes.BOOL

CreateEventA = kernel32.CreateEventA
CreateEventA.restype = wintypes.HANDLE

GetOverlappedResultEx = kernel32.GetOverlappedResultEx
GetOverlappedResultEx.restype = wintypes.BOOL

CloseHandle = kernel32.CloseHandle


def open_device_handle() -> int:
    """Open a handle to the Parsec VDD device via SetupDi enumeration."""
    dev_info = SetupDiGetClassDevsA(
        byref(VDD_ADAPTER_GUID), None, None, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE,
    )
    if dev_info is None or dev_info == INVALID_HANDLE_VALUE:
        raise OSError("Could not find Parsec VDD device. Is the driver installed?")

    dev_interface = SP_DEVICE_INTERFACE_DATA()
    dev_interface.cbSize = sizeof(SP_DEVICE_INTERFACE_DATA)

    handle = None
    i = 0
    try:
        while True:
            if not SetupDiEnumDeviceInterfaces(
                dev_info, None, byref(VDD_ADAPTER_GUID), i, byref(dev_interface),
            ):
                break

            detail = SP_DEVICE_INTERFACE_DETAIL_DATA_A()
            # cbSize depends on architecture: 5 for 32-bit, 8 for 64-bit
            detail.cbSize = 8 if sizeof(ctypes.c_void_p) == 8 else 5
            detail_size = wintypes.DWORD(sizeof(detail))

            if SetupDiGetDeviceInterfaceDetailA(
                dev_info, byref(dev_interface), byref(detail), detail_size, byref(detail_size), None,
            ):
                h = CreateFileA(
                    detail.DevicePath,
                    GENERIC_READ | GENERIC_WRITE,
                    0x01 | 0x02,  # FILE_SHARE_READ | FILE_SHARE_WRITE
                    None,
                    OPEN_EXISTING,
                    FILE_ATTRIBUTE_NORMAL | FILE_FLAG_NO_BUFFERING
                    | FILE_FLAG_OVERLAPPED | FILE_FLAG_WRITE_THROUGH,
                    None,
                )
                if h and h != INVALID_HANDLE_VALUE:
                    handle = h
                    break

            i += 1
    finally:
        SetupDiDestroyDeviceInfoList(dev_info)

    if not handle:
        raise OSError("Could not find Parsec VDD device. Is the driver installed?")

    return handle


def _vdd_ioctl(handle: int, code: int, data=None, data_size: int = 0) -> int:
    """Send an IOCTL to the VDD device using overlapped I/O."""
    in_buffer = (ctypes.c_byte * 32)()
    if data is not None:
        ctypes.memmove(in_buffer, data, min(data_size, 32))

    out_buffer = wintypes.DWORD(0)
    overlapped = OVERLAPPED()
    overlapped.hEvent = CreateEventA(None, True, False, None)

    bytes_returned = wintypes.DWORD(0)
    DeviceIoControl(
        handle, code,
        byref(in_buffer), sizeof(in_buffer),
        byref(out_buffer), sizeof(out_buffer),
        None, byref(overlapped),
    )

    success = GetOverlappedResultEx(handle, byref(overlapped), byref(bytes_returned), 5000, False)
    if overlapped.hEvent:
        CloseHandle(overlapped.hEvent)

    if not success:
        return -1
    return out_buffer.value


def vdd_add_display(handle: int) -> int:
    """Add a virtual display. Returns the display index."""
    idx = _vdd_ioctl(handle, VDD_IOCTL_ADD)
    if idx < 0:
        raise OSError("Failed to create virtual display")
    vdd_update(handle)
    return idx


def vdd_remove_display(handle: int, index: int):
    """Remove a virtual display by index."""
    # 16-bit big-endian index encoding
    index_be = ((index & 0xFF) << 8) | ((index >> 8) & 0xFF)
    data = ctypes.c_uint16(index_be)
    _vdd_ioctl(handle, VDD_IOCTL_REMOVE, byref(data), sizeof(data))
    vdd_update(handle)


def vdd_update(handle: int):
    """Ping the driver to keep displays alive. Must be called every <100ms."""
    _vdd_ioctl(handle, VDD_IOCTL_UPDATE)


def vdd_version(handle: int) -> int:
    """Query the driver minor version."""
    return _vdd_ioctl(handle, VDD_IOCTL_VERSION)


class ParsecVDD:
    """High-level Parsec VDD manager with automatic keep-alive thread."""

    def __init__(self):
        self.handle = open_device_handle()
        self._displays: list[int] = []
        self._alive = True
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._keepalive, daemon=True)
        self._thread.start()
        logger.info(f"Parsec VDD opened, driver version: {self.version()}")

    def _keepalive(self):
        """Background thread that pings the driver every 50ms."""
        while self._alive:
            try:
                vdd_update(self.handle)
            except Exception:
                logger.warning("VDD keep-alive ping failed")
            time.sleep(0.05)

    def add_display(self) -> int:
        """Create a virtual display. Returns the display index."""
        with self._lock:
            idx = vdd_add_display(self.handle)
            self._displays.append(idx)
            logger.info(f"Virtual display created at index {idx}")
            return idx

    def remove_display(self, index: int):
        """Remove a virtual display by index."""
        with self._lock:
            vdd_remove_display(self.handle, index)
            if index in self._displays:
                self._displays.remove(index)
            logger.info(f"Virtual display removed at index {index}")

    def remove_all(self):
        """Remove all virtual displays created by this instance."""
        with self._lock:
            for idx in list(self._displays):
                try:
                    vdd_remove_display(self.handle, idx)
                except Exception:
                    logger.warning(f"Failed to remove display {idx}")
            self._displays.clear()

    def version(self) -> int:
        return vdd_version(self.handle)

    @property
    def active_displays(self) -> list[int]:
        return list(self._displays)

    def close(self):
        """Stop keep-alive and close the device handle."""
        self._alive = False
        self._thread.join(timeout=2)
        self.remove_all()
        CloseHandle(self.handle)
        logger.info("Parsec VDD closed")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_driver.py -v
```

Expected: PASS for mock tests, SKIP for hardware tests.

- [ ] **Step 5: Commit**

```bash
git add src/windowsmcp_custom/display/ tests/test_driver.py
git commit -m "feat: Parsec VDD driver wrapper with keep-alive thread"
```

---

### Task 4: Display Manager

**Files:**
- Create: `src/windowsmcp_custom/display/manager.py`
- Create: `src/windowsmcp_custom/display/identity.py`
- Create: `tests/test_display_manager.py`

- [ ] **Step 1: Write tests for display manager**

Create `tests/test_display_manager.py`:
```python
"""Tests for virtual display manager."""

import json
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from windowsmcp_custom.display.manager import DisplayManager, DisplayInfo


class TestDisplayInfo:
    def test_contains_point_inside(self):
        info = DisplayInfo(device_name=r"\\.\DISPLAY3", x=3840, y=0, width=1920, height=1080)
        assert info.contains_point(4000, 500)

    def test_contains_point_outside(self):
        info = DisplayInfo(device_name=r"\\.\DISPLAY3", x=3840, y=0, width=1920, height=1080)
        assert not info.contains_point(100, 500)

    def test_contains_point_boundary(self):
        info = DisplayInfo(device_name=r"\\.\DISPLAY3", x=3840, y=0, width=1920, height=1080)
        assert info.contains_point(3840, 0)      # top-left inclusive
        assert not info.contains_point(5760, 0)   # right edge exclusive

    def test_to_relative(self):
        info = DisplayInfo(device_name=r"\\.\DISPLAY3", x=3840, y=0, width=1920, height=1080)
        rx, ry = info.to_relative(4340, 300)
        assert rx == 500
        assert ry == 300

    def test_to_absolute(self):
        info = DisplayInfo(device_name=r"\\.\DISPLAY3", x=3840, y=0, width=1920, height=1080)
        ax, ay = info.to_absolute(500, 300)
        assert ax == 4340
        assert ay == 300


class TestDisplayManagerEnumerate:
    @patch("windowsmcp_custom.display.manager.win32api")
    def test_enumerate_monitors(self, mock_api):
        mock_api.EnumDisplayMonitors.return_value = [
            (1, None, (0, 0, 1920, 1080)),
            (2, None, (1920, 0, 3840, 1080)),
        ]
        mock_api.EnumDisplayDevices.side_effect = [
            MagicMock(DeviceName=r"\\.\DISPLAY1", DeviceString="Monitor 1", StateFlags=1),
            MagicMock(DeviceName=r"\\.\DISPLAY2", DeviceString="Monitor 2", StateFlags=1),
            Exception("no more"),
        ]

        mgr = DisplayManager.__new__(DisplayManager)
        mgr._vdd = None
        mgr._agent_display = None
        mgr._state_file = Path("/tmp/test-state.json")

        displays = mgr.enumerate_monitors()
        assert len(displays) == 2
        assert displays[0].width == 1920
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_display_manager.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement DisplayManager**

Create `src/windowsmcp_custom/display/identity.py`:
```python
"""Display state persistence for crash recovery."""

import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path

logger = logging.getLogger(__name__)

STATE_DIR = Path.home() / ".windowsmcp"
STATE_FILE = STATE_DIR / "display-state.json"


@dataclass
class PersistedDisplayState:
    device_name: str
    display_index: int
    width: int
    height: int
    created_at: str  # ISO timestamp


def save_state(state: PersistedDisplayState):
    """Persist display state for crash recovery."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(asdict(state), indent=2))
    logger.info(f"Display state saved: {state.device_name} index={state.display_index}")


def load_state() -> PersistedDisplayState | None:
    """Load persisted display state. Returns None if no state exists."""
    if not STATE_FILE.exists():
        return None
    try:
        data = json.loads(STATE_FILE.read_text())
        return PersistedDisplayState(**data)
    except Exception as e:
        logger.warning(f"Failed to load display state: {e}")
        return None


def clear_state():
    """Remove persisted display state."""
    if STATE_FILE.exists():
        STATE_FILE.unlink()
        logger.info("Display state cleared")
```

Create `src/windowsmcp_custom/display/manager.py`:
```python
"""Virtual display lifecycle manager.

Creates, tracks, and destroys the agent's virtual display.
Handles display enumeration, bounds detection, and state persistence.
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import win32api
import win32con

from windowsmcp_custom.display.driver import ParsecVDD
from windowsmcp_custom.display.identity import (
    PersistedDisplayState, save_state, load_state, clear_state,
)

logger = logging.getLogger(__name__)


@dataclass
class DisplayInfo:
    """Information about a single display/monitor."""

    device_name: str
    x: int
    y: int
    width: int
    height: int
    is_agent: bool = False

    @property
    def left(self) -> int:
        return self.x

    @property
    def top(self) -> int:
        return self.y

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    def contains_point(self, px: int, py: int) -> bool:
        """Check if a point is within this display's bounds."""
        return self.left <= px < self.right and self.top <= py < self.bottom

    def to_relative(self, abs_x: int, abs_y: int) -> tuple[int, int]:
        """Convert absolute screen coords to display-relative coords."""
        return abs_x - self.x, abs_y - self.y

    def to_absolute(self, rel_x: int, rel_y: int) -> tuple[int, int]:
        """Convert display-relative coords to absolute screen coords."""
        return rel_x + self.x, rel_y + self.y


class DisplayManager:
    """Manages the agent's virtual display lifecycle."""

    def __init__(self):
        self._vdd: ParsecVDD | None = None
        self._agent_display: DisplayInfo | None = None
        self._display_index: int | None = None

    @property
    def agent_display(self) -> DisplayInfo | None:
        """The agent's virtual display info, or None if not created."""
        return self._agent_display

    @property
    def is_ready(self) -> bool:
        """Whether the agent display is active and bounds are known."""
        return self._agent_display is not None

    def check_driver(self) -> bool:
        """Check if Parsec VDD driver is installed."""
        try:
            vdd = ParsecVDD()
            vdd.close()
            return True
        except OSError:
            return False

    def create_display(self, width: int = 1920, height: int = 1080) -> DisplayInfo:
        """Create a virtual display for the agent.

        Returns DisplayInfo with the new display's bounds.
        Raises OSError if the driver is not installed or creation fails.
        """
        if self._agent_display is not None:
            raise RuntimeError("Agent display already exists. Destroy it first.")

        # Check for existing display from crash recovery
        saved = load_state()
        if saved:
            existing = self._find_display_by_name(saved.device_name)
            if existing:
                logger.info(f"Recovered existing display: {saved.device_name}")
                self._agent_display = existing
                self._agent_display.is_agent = True
                return self._agent_display
            else:
                logger.info("Stale display state found, creating fresh")
                clear_state()

        # Create VDD and add display
        self._vdd = ParsecVDD()
        self._display_index = self._vdd.add_display()

        # Wait for Windows to register the new display
        time.sleep(1.0)

        # Set resolution
        new_display = self._find_new_display()
        if new_display is None:
            raise OSError("Virtual display created but not found in display enumeration")

        self._set_resolution(new_display.device_name, width, height)
        time.sleep(0.5)

        # Re-enumerate to get final bounds
        new_display = self._find_display_by_name(new_display.device_name)
        if new_display is None:
            raise OSError("Virtual display lost after resolution change")

        new_display.is_agent = True
        self._agent_display = new_display

        # Persist for crash recovery
        save_state(PersistedDisplayState(
            device_name=new_display.device_name,
            display_index=self._display_index,
            width=width,
            height=height,
            created_at=datetime.now(timezone.utc).isoformat(),
        ))

        logger.info(
            f"Agent display ready: {new_display.device_name} "
            f"at ({new_display.x}, {new_display.y}) {width}x{height}"
        )
        return new_display

    def destroy_display(self):
        """Destroy the agent's virtual display.

        Moves any windows on the agent screen to the primary monitor first.
        """
        if self._agent_display is None:
            return

        # Move windows off agent screen before destroying
        self._migrate_windows_to_primary()

        if self._vdd and self._display_index is not None:
            try:
                self._vdd.remove_display(self._display_index)
            except Exception as e:
                logger.warning(f"Failed to remove display: {e}")

        if self._vdd:
            try:
                self._vdd.close()
            except Exception:
                pass

        self._vdd = None
        self._agent_display = None
        self._display_index = None
        clear_state()
        logger.info("Agent display destroyed")

    def enumerate_monitors(self) -> list[DisplayInfo]:
        """Enumerate all active monitors with their bounds."""
        monitors = win32api.EnumDisplayMonitors(None, None)
        displays = []
        for hMonitor, _hdcMonitor, rect in monitors:
            left, top, right, bottom = rect
            # Find device name for this monitor region
            device_name = self._device_name_for_rect(left, top, right, bottom)
            info = DisplayInfo(
                device_name=device_name or f"unknown_{left}_{top}",
                x=left,
                y=top,
                width=right - left,
                height=bottom - top,
                is_agent=(
                    self._agent_display is not None
                    and self._agent_display.device_name == device_name
                ),
            )
            displays.append(info)
        return displays

    def refresh_bounds(self):
        """Re-detect agent display bounds after a topology change."""
        if self._agent_display is None:
            return
        updated = self._find_display_by_name(self._agent_display.device_name)
        if updated:
            updated.is_agent = True
            self._agent_display = updated
            logger.info(f"Agent bounds refreshed: ({updated.x}, {updated.y})")
        else:
            logger.warning("Agent display no longer found after topology change")
            self._agent_display = None

    def _find_new_display(self) -> DisplayInfo | None:
        """Find a Parsec VDD display in the monitor list."""
        i = 0
        while True:
            try:
                dev = win32api.EnumDisplayDevices(None, i, 0)
                if "ParsecVDA" in dev.DeviceString or "PSCCDD" in (dev.DeviceID or ""):
                    if dev.StateFlags & win32con.DISPLAY_DEVICE_ACTIVE:
                        return self._find_display_by_name(dev.DeviceName)
                i += 1
            except Exception:
                break
        return None

    def _find_display_by_name(self, device_name: str) -> DisplayInfo | None:
        """Find a display by its device name."""
        for d in self.enumerate_monitors():
            if d.device_name == device_name:
                return d
        return None

    def _device_name_for_rect(
        self, left: int, top: int, right: int, bottom: int,
    ) -> str | None:
        """Match a monitor rect to a device name via EnumDisplayDevices."""
        i = 0
        while True:
            try:
                dev = win32api.EnumDisplayDevices(None, i, 0)
                if dev.StateFlags & win32con.DISPLAY_DEVICE_ACTIVE:
                    settings = win32api.EnumDisplaySettings(
                        dev.DeviceName, win32con.ENUM_CURRENT_SETTINGS,
                    )
                    if settings:
                        pos_x = getattr(settings, "Position_x", 0)
                        pos_y = getattr(settings, "Position_y", 0)
                        if pos_x == left and pos_y == top:
                            return dev.DeviceName
                i += 1
            except Exception:
                break
        return None

    def _set_resolution(self, device_name: str, width: int, height: int):
        """Set the resolution of a display."""
        try:
            settings = win32api.EnumDisplaySettings(
                device_name, win32con.ENUM_CURRENT_SETTINGS,
            )
            settings.PelsWidth = width
            settings.PelsHeight = height
            settings.Fields = win32con.DM_PELSWIDTH | win32con.DM_PELSHEIGHT
            result = win32api.ChangeDisplaySettingsEx(
                device_name, settings, win32con.CDS_UPDATEREGISTRY,
            )
            if result != win32con.DISP_CHANGE_SUCCESSFUL:
                logger.warning(f"Resolution change returned {result}")
        except Exception as e:
            logger.warning(f"Failed to set resolution for {device_name}: {e}")

    def _migrate_windows_to_primary(self):
        """Move all windows from agent screen to primary monitor."""
        if self._agent_display is None:
            return

        from windowsmcp_custom.uia.controls import (
            enumerate_windows, get_window_rect, move_window, is_window_visible,
        )

        agent = self._agent_display
        for hwnd in enumerate_windows():
            if not is_window_visible(hwnd):
                continue
            rect = get_window_rect(hwnd)
            if rect is None:
                continue
            left, top, right, bottom = rect
            center_x = (left + right) // 2
            center_y = (top + bottom) // 2
            if agent.contains_point(center_x, center_y):
                # Move to primary monitor origin, preserving size
                w = right - left
                h = bottom - top
                move_window(hwnd, 100, 100, w, h)
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_display_manager.py -v
```

Expected: PASS for unit tests.

- [ ] **Step 5: Commit**

```bash
git add src/windowsmcp_custom/display/ tests/test_display_manager.py
git commit -m "feat: display manager with lifecycle, enumeration, crash recovery"
```

---

### Task 5: Confinement Engine

**Files:**
- Create: `src/windowsmcp_custom/confinement/__init__.py`
- Create: `src/windowsmcp_custom/confinement/engine.py`
- Create: `src/windowsmcp_custom/confinement/bounds.py`
- Create: `tests/test_confinement.py`

- [ ] **Step 1: Write tests for confinement engine**

Create `tests/test_confinement.py`:
```python
"""Tests for the confinement engine."""

import pytest
from windowsmcp_custom.confinement.engine import (
    ConfinementEngine, ConfinementError, ActionType,
)
from tests.conftest import MockBounds


@pytest.fixture
def engine():
    e = ConfinementEngine()
    e.set_agent_bounds(MockBounds(x=3840, y=0, width=1920, height=1080))
    return e


class TestActionClassification:
    def test_classify_read_tools(self, engine):
        assert engine.classify_action("Screenshot") == ActionType.READ
        assert engine.classify_action("Snapshot") == ActionType.READ

    def test_classify_write_tools(self, engine):
        assert engine.classify_action("Click") == ActionType.WRITE
        assert engine.classify_action("Type") == ActionType.WRITE
        assert engine.classify_action("Move") == ActionType.WRITE
        assert engine.classify_action("Scroll") == ActionType.WRITE
        assert engine.classify_action("Shortcut") == ActionType.WRITE
        assert engine.classify_action("App") == ActionType.WRITE
        assert engine.classify_action("MultiSelect") == ActionType.WRITE
        assert engine.classify_action("MultiEdit") == ActionType.WRITE

    def test_classify_unconfined_tools(self, engine):
        assert engine.classify_action("PowerShell") == ActionType.UNCONFINED
        assert engine.classify_action("FileSystem") == ActionType.UNCONFINED
        assert engine.classify_action("Clipboard") == ActionType.UNCONFINED


class TestCoordinateValidation:
    def test_valid_relative_coords(self, engine):
        ax, ay = engine.validate_and_translate(500, 300)
        assert ax == 4340
        assert ay == 300

    def test_origin(self, engine):
        ax, ay = engine.validate_and_translate(0, 0)
        assert ax == 3840
        assert ay == 0

    def test_max_bounds(self, engine):
        ax, ay = engine.validate_and_translate(1919, 1079)
        assert ax == 5759
        assert ay == 1079

    def test_out_of_bounds_x(self, engine):
        with pytest.raises(ConfinementError, match="out of bounds"):
            engine.validate_and_translate(1920, 500)

    def test_out_of_bounds_negative(self, engine):
        with pytest.raises(ConfinementError, match="out of bounds"):
            engine.validate_and_translate(-1, 500)

    def test_no_agent_display(self):
        engine = ConfinementEngine()
        with pytest.raises(ConfinementError, match="no agent display"):
            engine.validate_and_translate(100, 100)


class TestPointOnAgentScreen:
    def test_absolute_point_on_agent(self, engine):
        assert engine.is_point_on_agent_screen(4000, 500)

    def test_absolute_point_on_user(self, engine):
        assert not engine.is_point_on_agent_screen(100, 500)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_confinement.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement confinement engine**

Create `src/windowsmcp_custom/confinement/__init__.py`:
```python
"""Confinement engine for restricting agent GUI actions to the virtual display."""
```

Create `src/windowsmcp_custom/confinement/bounds.py`:
```python
"""Screen bounds tracking and display change monitoring."""

import ctypes
import ctypes.wintypes as wintypes
import logging
import threading

logger = logging.getLogger(__name__)

WM_DISPLAYCHANGE = 0x007E
WM_WTSSESSION_CHANGE = 0x02B1
WTS_SESSION_LOCK = 0x7
WTS_SESSION_UNLOCK = 0x8


class DisplayChangeListener:
    """Listens for WM_DISPLAYCHANGE via a hidden message-only window on a dedicated thread."""

    def __init__(self, on_display_change=None, on_session_change=None):
        self._on_display_change = on_display_change
        self._on_session_change = on_session_change
        self._thread: threading.Thread | None = None
        self._hwnd = None
        self._running = False

    def start(self):
        """Start the listener thread."""
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the listener thread."""
        self._running = False
        if self._hwnd:
            ctypes.windll.user32.PostMessageW(self._hwnd, 0x0012, 0, 0)  # WM_QUIT
        if self._thread:
            self._thread.join(timeout=2)

    def _run(self):
        """Message pump on a dedicated thread."""
        WNDPROC = ctypes.WINFUNCTYPE(
            ctypes.c_long, ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p,
        )

        def wndproc(hwnd, msg, wparam, lparam):
            if msg == WM_DISPLAYCHANGE:
                if self._on_display_change:
                    try:
                        self._on_display_change()
                    except Exception:
                        logger.exception("Error in display change callback")
            elif msg == WM_WTSSESSION_CHANGE:
                if self._on_session_change:
                    try:
                        self._on_session_change(wparam)
                    except Exception:
                        logger.exception("Error in session change callback")
            return ctypes.windll.user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._wndproc = WNDPROC(wndproc)  # prevent GC

        wc = wintypes.WNDCLASSW()
        wc.lpfnWndProc = self._wndproc
        wc.lpszClassName = "WindowsMCPDisplayListener"
        wc.hInstance = ctypes.windll.kernel32.GetModuleHandleW(None)
        ctypes.windll.user32.RegisterClassW(ctypes.byref(wc))

        HWND_MESSAGE = ctypes.c_void_p(-3)
        self._hwnd = ctypes.windll.user32.CreateWindowExW(
            0, wc.lpszClassName, "WindowsMCPListener",
            0, 0, 0, 0, 0, HWND_MESSAGE, None, wc.hInstance, None,
        )

        # Register for session notifications
        try:
            ctypes.windll.wtsapi32.WTSRegisterSessionNotification(
                self._hwnd, 0,  # NOTIFY_FOR_THIS_SESSION
            )
        except Exception:
            logger.debug("WTSRegisterSessionNotification not available")

        # Message loop
        msg = wintypes.MSG()
        while self._running:
            ret = ctypes.windll.user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret <= 0:
                break
            ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
            ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))
```

Create `src/windowsmcp_custom/confinement/engine.py`:
```python
"""Confinement engine — validates and translates agent actions to the virtual display."""

import logging
from enum import Enum
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class ActionType(Enum):
    READ = "read"           # Screenshot, Snapshot — allowed on all screens
    WRITE = "write"         # Click, Type, Move, Scroll, etc. — agent screen only
    UNCONFINED = "unconfined"  # PowerShell, FileSystem, etc. — no screen confinement


class ConfinementError(Exception):
    """Raised when an action violates confinement bounds."""
    pass


# Tool name → action type mapping
_TOOL_ACTIONS: dict[str, ActionType] = {
    "Screenshot": ActionType.READ,
    "Snapshot": ActionType.READ,
    "Scrape": ActionType.READ,
    "Click": ActionType.WRITE,
    "Type": ActionType.WRITE,
    "Move": ActionType.WRITE,
    "Scroll": ActionType.WRITE,
    "Shortcut": ActionType.WRITE,
    "App": ActionType.WRITE,
    "Wait": ActionType.UNCONFINED,
    "MultiSelect": ActionType.WRITE,
    "MultiEdit": ActionType.WRITE,
    "Notification": ActionType.UNCONFINED,
    "PowerShell": ActionType.UNCONFINED,
    "FileSystem": ActionType.UNCONFINED,
    "Clipboard": ActionType.UNCONFINED,
    "Process": ActionType.UNCONFINED,
    "Registry": ActionType.UNCONFINED,
    "CreateScreen": ActionType.UNCONFINED,
    "DestroyScreen": ActionType.UNCONFINED,
    "ScreenInfo": ActionType.READ,
    "RecoverWindow": ActionType.WRITE,  # Special: can move windows FROM other screens
}


@dataclass
class ScreenBounds:
    """Agent screen bounds in absolute Windows coordinates."""
    x: int
    y: int
    width: int
    height: int

    @property
    def left(self) -> int:
        return self.x

    @property
    def top(self) -> int:
        return self.y

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height


class ConfinementEngine:
    """Core confinement logic — validates coordinates and translates between
    agent-relative and absolute coordinate systems."""

    def __init__(self):
        self._bounds: ScreenBounds | None = None

    @property
    def bounds(self) -> ScreenBounds | None:
        return self._bounds

    def set_agent_bounds(self, bounds) -> None:
        """Set agent screen bounds. Accepts any object with x, y, width, height."""
        self._bounds = ScreenBounds(
            x=bounds.x, y=bounds.y, width=bounds.width, height=bounds.height,
        )
        logger.info(
            f"Agent bounds set: ({self._bounds.x}, {self._bounds.y}) "
            f"{self._bounds.width}x{self._bounds.height}"
        )

    def clear_bounds(self) -> None:
        """Clear agent screen bounds (display destroyed)."""
        self._bounds = None

    def classify_action(self, tool_name: str) -> ActionType:
        """Classify a tool action as READ, WRITE, or UNCONFINED."""
        return _TOOL_ACTIONS.get(tool_name, ActionType.UNCONFINED)

    def validate_and_translate(self, rel_x: int, rel_y: int) -> tuple[int, int]:
        """Validate agent-relative coordinates and translate to absolute.

        Args:
            rel_x: X coordinate relative to agent screen (0 to width-1)
            rel_y: Y coordinate relative to agent screen (0 to height-1)

        Returns:
            Tuple of (absolute_x, absolute_y) in Windows screen coordinates.

        Raises:
            ConfinementError: If coordinates are out of agent screen bounds.
        """
        if self._bounds is None:
            raise ConfinementError(
                "Cannot validate coordinates: no agent display active. "
                "Call CreateScreen first."
            )

        if rel_x < 0 or rel_x >= self._bounds.width or rel_y < 0 or rel_y >= self._bounds.height:
            raise ConfinementError(
                f"Coordinates ({rel_x}, {rel_y}) are out of bounds. "
                f"Agent screen is {self._bounds.width}x{self._bounds.height} "
                f"(valid range: 0-{self._bounds.width - 1}, 0-{self._bounds.height - 1})."
            )

        abs_x = rel_x + self._bounds.x
        abs_y = rel_y + self._bounds.y
        return abs_x, abs_y

    def is_point_on_agent_screen(self, abs_x: int, abs_y: int) -> bool:
        """Check if an absolute point is on the agent's screen."""
        if self._bounds is None:
            return False
        return (
            self._bounds.left <= abs_x < self._bounds.right
            and self._bounds.top <= abs_y < self._bounds.bottom
        )

    def validate_absolute_point(self, abs_x: int, abs_y: int) -> None:
        """Validate that an absolute point is on the agent screen.

        Raises ConfinementError if out of bounds.
        """
        if not self.is_point_on_agent_screen(abs_x, abs_y):
            raise ConfinementError(
                f"Absolute point ({abs_x}, {abs_y}) is not on the agent screen. "
                f"Agent screen bounds: ({self._bounds.left}, {self._bounds.top}) to "
                f"({self._bounds.right - 1}, {self._bounds.bottom - 1})."
            )
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_confinement.py -v
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add src/windowsmcp_custom/confinement/ tests/test_confinement.py
git commit -m "feat: confinement engine with bounds validation and coord translation"
```

---

### Task 6: Shortcut Filtering

**Files:**
- Create: `src/windowsmcp_custom/confinement/shortcuts.py`

- [ ] **Step 1: Implement shortcut filter**

Create `src/windowsmcp_custom/confinement/shortcuts.py`:
```python
"""Shortcut allowlist/blocklist for preventing global system shortcuts."""

import logging

logger = logging.getLogger(__name__)

# Shortcuts that affect the entire desktop session — always blocked
BLOCKED_SHORTCUTS = frozenset({
    "win+d",          # Show desktop
    "win+tab",        # Task view
    "win+l",          # Lock screen
    "win+r",          # Run dialog
    "win+e",          # File Explorer
    "win+m",          # Minimize all
    "win+shift+m",    # Restore minimized
    "alt+tab",        # Switch window (session-global)
    "alt+shift+tab",
    "alt+f4",         # Close window — allowed per-window, but risky if focus is wrong
    "ctrl+alt+del",   # Secure desktop
    "ctrl+shift+esc", # Task manager
    "win+ctrl+d",     # New virtual desktop
    "win+ctrl+left",  # Switch virtual desktop
    "win+ctrl+right",
    "win+ctrl+f4",    # Close virtual desktop
})

# Shortcuts that are safe for app-level use — always allowed
ALLOWED_SHORTCUTS = frozenset({
    "ctrl+c", "ctrl+x", "ctrl+v", "ctrl+z", "ctrl+y",
    "ctrl+a", "ctrl+s", "ctrl+f", "ctrl+p", "ctrl+n",
    "ctrl+w", "ctrl+t", "ctrl+shift+t",
    "ctrl+tab", "ctrl+shift+tab",
    "ctrl+shift+n",
    "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12",
    "enter", "escape", "tab", "backspace", "delete",
    "home", "end", "pageup", "pagedown",
    "up", "down", "left", "right",
    "shift+tab",
})


def normalize_shortcut(shortcut: str) -> str:
    """Normalize a shortcut string to lowercase with consistent modifier order."""
    parts = [p.strip().lower() for p in shortcut.split("+")]
    modifiers = sorted([p for p in parts if p in ("ctrl", "alt", "shift", "win")])
    keys = [p for p in parts if p not in ("ctrl", "alt", "shift", "win")]
    return "+".join(modifiers + keys)


def is_shortcut_allowed(shortcut: str) -> bool:
    """Check if a keyboard shortcut is allowed for the agent.

    Returns True if the shortcut is safe for app-level use.
    Returns False if the shortcut would affect the global desktop session.
    """
    normalized = normalize_shortcut(shortcut)

    if normalized in BLOCKED_SHORTCUTS:
        return False

    if normalized in ALLOWED_SHORTCUTS:
        return True

    # Shortcuts with 'win' modifier are blocked by default (system-level)
    if "win" in normalized.split("+"):
        return False

    # Unknown shortcuts: allow by default (app-level assumed)
    return True


def get_blocked_reason(shortcut: str) -> str:
    """Get a human-readable reason why a shortcut is blocked."""
    normalized = normalize_shortcut(shortcut)

    if "win" in normalized.split("+"):
        return (
            f"Shortcut '{shortcut}' is blocked because Win+key shortcuts affect "
            "the entire desktop session. Use the App tool to manage windows instead."
        )

    if normalized in BLOCKED_SHORTCUTS:
        return (
            f"Shortcut '{shortcut}' is blocked because it affects the entire desktop "
            "session and could interfere with the user's workspace."
        )

    return f"Shortcut '{shortcut}' is blocked by the confinement engine."
```

- [ ] **Step 2: Commit**

```bash
git add src/windowsmcp_custom/confinement/shortcuts.py
git commit -m "feat: shortcut filtering — allowlist/blocklist for system shortcuts"
```

---

### Task 7: Screen Management MCP Tools

**Files:**
- Create: `src/windowsmcp_custom/tools/__init__.py`
- Create: `src/windowsmcp_custom/tools/screen.py`

- [ ] **Step 1: Create tool registry**

Create `src/windowsmcp_custom/tools/__init__.py`:
```python
"""MCP tool registry."""

from windowsmcp_custom.tools import (
    screen, screenshot, input, app, multi,
    shell, filesystem, clipboard, process, registry, notification, scrape,
)

_MODULES = [
    screen, screenshot, input, app, multi,
    shell, filesystem, clipboard, process, registry, notification, scrape,
]


def register_all(mcp, *, get_display_manager, get_confinement):
    """Register all tool modules on the FastMCP server."""
    for mod in _MODULES:
        mod.register(mcp, get_display_manager=get_display_manager, get_confinement=get_confinement)
```

- [ ] **Step 2: Implement screen management tools**

Create `src/windowsmcp_custom/tools/screen.py`:
```python
"""Screen management MCP tools: CreateScreen, DestroyScreen, ScreenInfo, RecoverWindow."""

import re
import logging
from fastmcp import Context

logger = logging.getLogger(__name__)


def register(mcp, *, get_display_manager, get_confinement):

    @mcp.tool(
        name="CreateScreen",
        description=(
            "Create the agent's virtual display screen. Call this once at the start of a session "
            "before using any GUI tools. The agent operates exclusively on this screen.\n\n"
            "Parameters:\n"
            "- width: Screen width in pixels (default 1920, min 1280, max 1920)\n"
            "- height: Screen height in pixels (default 1080, min 720, max 1080)"
        ),
    )
    def create_screen(
        width: int = 1920,
        height: int = 1080,
        ctx: Context = None,
    ) -> str:
        dm = get_display_manager()
        ce = get_confinement()

        width = max(1280, min(1920, width))
        height = max(720, min(1080, height))

        try:
            display = dm.create_display(width=width, height=height)
            ce.set_agent_bounds(display)
            return (
                f"Agent screen created: {display.width}x{display.height}\n"
                f"Screen bounds: (0, 0) to ({display.width - 1}, {display.height - 1})\n"
                f"Use agent-relative coordinates (0,0 is top-left of your screen).\n"
                f"You can now use Screenshot, Click, Type, and other GUI tools."
            )
        except OSError as e:
            return f"Failed to create screen: {e}"

    @mcp.tool(
        name="DestroyScreen",
        description="Remove the agent's virtual display. Windows on the agent screen are moved to the user's primary monitor.",
    )
    def destroy_screen(ctx: Context = None) -> str:
        dm = get_display_manager()
        ce = get_confinement()

        dm.destroy_display()
        ce.clear_bounds()
        return "Agent screen destroyed. All windows moved to primary monitor."

    @mcp.tool(
        name="ScreenInfo",
        description="Get information about all screens, including the agent screen bounds and which screen is the agent's.",
    )
    def screen_info(ctx: Context = None) -> str:
        dm = get_display_manager()
        monitors = dm.enumerate_monitors()

        lines = ["Screens:\n"]
        for i, m in enumerate(monitors):
            role = " [AGENT]" if m.is_agent else ""
            lines.append(
                f"  {i + 1}. {m.device_name}{role}: "
                f"({m.x}, {m.y}) {m.width}x{m.height}"
            )

        agent = dm.agent_display
        if agent:
            lines.append(
                f"\nAgent screen: {agent.width}x{agent.height} "
                f"(use coordinates 0-{agent.width - 1}, 0-{agent.height - 1})"
            )
        else:
            lines.append("\nNo agent screen active. Call CreateScreen first.")

        return "\n".join(lines)

    @mcp.tool(
        name="RecoverWindow",
        description=(
            "Move a window from any screen to the agent's screen. Useful for recovering "
            "pop-ups or dialogs that appear on the user's monitors.\n\n"
            "Selectors (provide at least one):\n"
            "- title: Window title (supports regex)\n"
            "- pid: Process ID\n"
            "- process_name: Process executable name (e.g. 'chrome.exe')\n"
            "- class_name: Window class name"
        ),
    )
    def recover_window(
        title: str | None = None,
        pid: int | None = None,
        process_name: str | None = None,
        class_name: str | None = None,
        ctx: Context = None,
    ) -> str:
        dm = get_display_manager()
        agent = dm.agent_display
        if agent is None:
            return "No agent screen active. Call CreateScreen first."

        if not any([title, pid, process_name, class_name]):
            return "Provide at least one selector: title, pid, process_name, or class_name."

        from windowsmcp_custom.uia.controls import (
            enumerate_windows, get_window_title, get_window_pid,
            get_window_class, get_window_rect, move_window, is_window_visible,
        )
        import psutil

        matches = []
        for hwnd in enumerate_windows():
            if not is_window_visible(hwnd):
                continue

            match = True
            if title:
                wt = get_window_title(hwnd)
                if not re.search(title, wt, re.IGNORECASE):
                    match = False
            if pid and match:
                if get_window_pid(hwnd) != pid:
                    match = False
            if process_name and match:
                wp = get_window_pid(hwnd)
                try:
                    proc = psutil.Process(wp)
                    if proc.name().lower() != process_name.lower():
                        match = False
                except Exception:
                    match = False
            if class_name and match:
                if get_window_class(hwnd).lower() != class_name.lower():
                    match = False

            if match:
                matches.append(hwnd)

        if not matches:
            return "No windows matched the given selectors."

        if len(matches) > 5:
            return (
                f"Too many matches ({len(matches)} windows). "
                "Narrow your selectors to be more specific."
            )

        moved = 0
        for hwnd in matches:
            rect = get_window_rect(hwnd)
            if rect:
                w = rect[2] - rect[0]
                h = rect[3] - rect[1]
                # Center on agent screen
                target_x = agent.x + (agent.width - w) // 2
                target_y = agent.y + (agent.height - h) // 2
                move_window(hwnd, target_x, target_y, w, h)
                moved += 1

        wt = get_window_title(matches[0]) if matches else "unknown"
        return f"Moved {moved} window(s) to agent screen. First match: '{wt}'"
```

- [ ] **Step 3: Commit**

```bash
git add src/windowsmcp_custom/tools/__init__.py src/windowsmcp_custom/tools/screen.py
git commit -m "feat: screen management tools — CreateScreen, DestroyScreen, ScreenInfo, RecoverWindow"
```

---

### Task 8: Input MCP Tools

**Files:**
- Create: `src/windowsmcp_custom/tools/input.py`
- Create: `tests/test_tools_input.py`

- [ ] **Step 1: Write tests for input confinement**

Create `tests/test_tools_input.py`:
```python
"""Tests for input tool confinement."""

import pytest
from windowsmcp_custom.confinement.engine import ConfinementEngine, ConfinementError
from tests.conftest import MockBounds


@pytest.fixture
def engine():
    e = ConfinementEngine()
    e.set_agent_bounds(MockBounds(x=3840, y=0, width=1920, height=1080))
    return e


class TestClickConfinement:
    def test_valid_click_translates(self, engine):
        abs_x, abs_y = engine.validate_and_translate(960, 540)
        assert abs_x == 4800
        assert abs_y == 540

    def test_click_out_of_bounds_rejected(self, engine):
        with pytest.raises(ConfinementError):
            engine.validate_and_translate(2000, 500)


class TestShortcutConfinement:
    def test_allowed_shortcut(self):
        from windowsmcp_custom.confinement.shortcuts import is_shortcut_allowed
        assert is_shortcut_allowed("ctrl+c")
        assert is_shortcut_allowed("Ctrl+S")
        assert is_shortcut_allowed("F5")

    def test_blocked_shortcut(self):
        from windowsmcp_custom.confinement.shortcuts import is_shortcut_allowed
        assert not is_shortcut_allowed("alt+tab")
        assert not is_shortcut_allowed("win+d")
        assert not is_shortcut_allowed("ctrl+alt+del")
```

- [ ] **Step 2: Run tests to verify they pass (confinement) and fail (tools not yet created)**

```bash
uv run pytest tests/test_tools_input.py -v
```

- [ ] **Step 3: Implement input tools**

Create `src/windowsmcp_custom/tools/input.py`:
```python
"""Input MCP tools: Click, Type, Move, Scroll, Shortcut, Wait.

All GUI write tools validate coordinates against agent screen bounds
using agent-relative coordinates (0,0 = top-left of agent screen).
"""

import time
import logging
from fastmcp import Context

from windowsmcp_custom.confinement.engine import ConfinementError
from windowsmcp_custom.confinement.shortcuts import is_shortcut_allowed, get_blocked_reason

logger = logging.getLogger(__name__)


def register(mcp, *, get_display_manager, get_confinement):

    @mcp.tool(
        name="Click",
        description=(
            "Click at a position on the agent's screen using agent-relative coordinates.\n"
            "Coordinates are relative to the agent screen: (0,0) is top-left.\n\n"
            "Parameters:\n"
            "- x, y: Position on agent screen\n"
            "- button: 'left' (default), 'right', or 'middle'\n"
            "- clicks: Number of clicks (1=single, 2=double)"
        ),
    )
    def click(
        x: int,
        y: int,
        button: str = "left",
        clicks: int = 1,
        ctx: Context = None,
    ) -> str:
        ce = get_confinement()
        try:
            abs_x, abs_y = ce.validate_and_translate(x, y)
        except ConfinementError as e:
            return f"Click blocked: {e}"

        from windowsmcp_custom.uia.controls import click_at
        click_at(abs_x, abs_y, button=button, clicks=clicks)
        return f"Clicked ({x}, {y}) [{button}, {clicks}x]"

    @mcp.tool(
        name="Type",
        description=(
            "Type text at the current focus point or at a specific position on the agent screen.\n\n"
            "Parameters:\n"
            "- text: Text to type\n"
            "- x, y: Optional position to click before typing (agent-relative coords)\n"
            "- clear: If true, select all and delete before typing"
        ),
    )
    def type_text(
        text: str,
        x: int | None = None,
        y: int | None = None,
        clear: bool | str = False,
        ctx: Context = None,
    ) -> str:
        ce = get_confinement()
        clear = clear is True or (isinstance(clear, str) and clear.lower() == "true")

        # Click at position first if specified
        if x is not None and y is not None:
            try:
                abs_x, abs_y = ce.validate_and_translate(x, y)
            except ConfinementError as e:
                return f"Type blocked: {e}"
            from windowsmcp_custom.uia.controls import click_at
            click_at(abs_x, abs_y)
            time.sleep(0.1)

        from windowsmcp_custom.uia.controls import type_text as _type_text

        if clear:
            # Select all and delete
            from windowsmcp_custom.uia.core import (
                INPUT, INPUT_UNION, KEYBDINPUT, INPUT_KEYBOARD, KEYEVENTF_KEYUP, send_input,
            )
            # Ctrl+A
            ctrl_down = INPUT(type=INPUT_KEYBOARD, union=INPUT_UNION(
                ki=KEYBDINPUT(wVk=0x11)))  # VK_CONTROL
            a_down = INPUT(type=INPUT_KEYBOARD, union=INPUT_UNION(
                ki=KEYBDINPUT(wVk=0x41)))  # 'A'
            a_up = INPUT(type=INPUT_KEYBOARD, union=INPUT_UNION(
                ki=KEYBDINPUT(wVk=0x41, dwFlags=KEYEVENTF_KEYUP)))
            ctrl_up = INPUT(type=INPUT_KEYBOARD, union=INPUT_UNION(
                ki=KEYBDINPUT(wVk=0x11, dwFlags=KEYEVENTF_KEYUP)))
            send_input(ctrl_down, a_down, a_up, ctrl_up)
            time.sleep(0.05)

        _type_text(text)
        preview = text[:50] + "..." if len(text) > 50 else text
        return f"Typed: '{preview}'"

    @mcp.tool(
        name="Move",
        description=(
            "Move the mouse cursor to a position on the agent screen.\n"
            "Optionally drag from current position to the target.\n\n"
            "Parameters:\n"
            "- x, y: Target position (agent-relative)\n"
            "- drag: If true, hold left mouse button during move"
        ),
    )
    def move(
        x: int,
        y: int,
        drag: bool | str = False,
        ctx: Context = None,
    ) -> str:
        ce = get_confinement()
        drag = drag is True or (isinstance(drag, str) and drag.lower() == "true")

        try:
            abs_x, abs_y = ce.validate_and_translate(x, y)
        except ConfinementError as e:
            return f"Move blocked: {e}"

        from windowsmcp_custom.uia.controls import move_cursor
        from windowsmcp_custom.uia.core import (
            INPUT, INPUT_UNION, MOUSEINPUT, INPUT_MOUSE,
            MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP, send_input,
        )

        if drag:
            down = INPUT(type=INPUT_MOUSE, union=INPUT_UNION(
                mi=MOUSEINPUT(dwFlags=MOUSEEVENTF_LEFTDOWN)))
            send_input(down)

        move_cursor(abs_x, abs_y)

        if drag:
            up = INPUT(type=INPUT_MOUSE, union=INPUT_UNION(
                mi=MOUSEINPUT(dwFlags=MOUSEEVENTF_LEFTUP)))
            send_input(up)

        return f"{'Dragged' if drag else 'Moved'} to ({x}, {y})"

    @mcp.tool(
        name="Scroll",
        description=(
            "Scroll at a position on the agent screen.\n\n"
            "Parameters:\n"
            "- x, y: Position to scroll at (agent-relative)\n"
            "- amount: Scroll amount (positive=up, negative=down)\n"
            "- horizontal: If true, scroll horizontally"
        ),
    )
    def scroll(
        x: int,
        y: int,
        amount: int = -3,
        horizontal: bool | str = False,
        ctx: Context = None,
    ) -> str:
        ce = get_confinement()
        horizontal = horizontal is True or (isinstance(horizontal, str) and horizontal.lower() == "true")

        try:
            abs_x, abs_y = ce.validate_and_translate(x, y)
        except ConfinementError as e:
            return f"Scroll blocked: {e}"

        from windowsmcp_custom.uia.controls import scroll_at
        scroll_at(abs_x, abs_y, amount=amount, horizontal=horizontal)
        direction = "horizontally" if horizontal else "vertically"
        return f"Scrolled {direction} by {amount} at ({x}, {y})"

    @mcp.tool(
        name="Shortcut",
        description=(
            "Send a keyboard shortcut to the foreground window on the agent screen.\n"
            "System-wide shortcuts (Win+D, Alt+Tab, etc.) are blocked.\n\n"
            "Parameters:\n"
            "- keys: Shortcut string (e.g. 'ctrl+c', 'ctrl+shift+t', 'F5', 'enter')"
        ),
    )
    def shortcut(keys: str, ctx: Context = None) -> str:
        if not is_shortcut_allowed(keys):
            return f"Shortcut blocked: {get_blocked_reason(keys)}"

        # Parse shortcut into key events
        from windowsmcp_custom.uia.core import (
            INPUT, INPUT_UNION, KEYBDINPUT, INPUT_KEYBOARD, KEYEVENTF_KEYUP, send_input,
        )

        VK_MAP = {
            "ctrl": 0x11, "alt": 0x12, "shift": 0x10, "enter": 0x0D,
            "escape": 0x1B, "tab": 0x09, "backspace": 0x08, "delete": 0x2E,
            "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
            "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
            "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74,
            "f6": 0x75, "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79,
            "f11": 0x7A, "f12": 0x7B, "space": 0x20,
        }

        parts = [p.strip().lower() for p in keys.split("+")]
        vk_codes = []
        for part in parts:
            if part in VK_MAP:
                vk_codes.append(VK_MAP[part])
            elif len(part) == 1 and part.isalpha():
                vk_codes.append(ord(part.upper()))
            elif len(part) == 1 and part.isdigit():
                vk_codes.append(ord(part))
            else:
                return f"Unknown key in shortcut: '{part}'"

        # Press all keys down, then release in reverse
        downs = [INPUT(type=INPUT_KEYBOARD, union=INPUT_UNION(
            ki=KEYBDINPUT(wVk=vk))) for vk in vk_codes]
        ups = [INPUT(type=INPUT_KEYBOARD, union=INPUT_UNION(
            ki=KEYBDINPUT(wVk=vk, dwFlags=KEYEVENTF_KEYUP))) for vk in reversed(vk_codes)]
        send_input(*downs, *ups)
        return f"Sent shortcut: {keys}"

    @mcp.tool(
        name="Wait",
        description="Pause execution for the specified duration.\n\nParameters:\n- seconds: Duration to wait (max 30)",
    )
    def wait(seconds: float = 1.0, ctx: Context = None) -> str:
        seconds = max(0.1, min(30.0, seconds))
        time.sleep(seconds)
        return f"Waited {seconds}s"
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_tools_input.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/windowsmcp_custom/tools/input.py tests/test_tools_input.py
git commit -m "feat: input MCP tools — Click, Type, Move, Scroll, Shortcut, Wait with confinement"
```

---

### Task 9: Screenshot & Capture Tools

**Files:**
- Create: `src/windowsmcp_custom/display/capture.py`
- Create: `src/windowsmcp_custom/tools/screenshot.py`

- [ ] **Step 1: Implement screen capture module**

Create `src/windowsmcp_custom/display/capture.py`:
```python
"""Screen capture with fallback chain: dxcam → mss → Pillow."""

import base64
import io
import logging
from PIL import Image, ImageGrab

logger = logging.getLogger(__name__)

try:
    import dxcam
except ImportError:
    dxcam = None

try:
    import mss as mss_module
except ImportError:
    mss_module = None


def capture_region(
    left: int, top: int, right: int, bottom: int, backend: str = "auto",
) -> Image.Image:
    """Capture a screen region as a PIL Image.

    Args:
        left, top, right, bottom: Region in absolute screen coordinates.
        backend: "auto", "dxcam", "mss", or "pillow".
    """
    chain = ["dxcam", "mss", "pillow"] if backend == "auto" else [backend]

    for name in chain:
        try:
            if name == "dxcam" and dxcam is not None:
                return _capture_dxcam(left, top, right, bottom)
            elif name == "mss" and mss_module is not None:
                return _capture_mss(left, top, right, bottom)
            elif name == "pillow":
                return _capture_pillow(left, top, right, bottom)
        except Exception as e:
            logger.warning(f"Capture backend '{name}' failed: {e}")

    return _capture_pillow(left, top, right, bottom)


def _capture_pillow(left: int, top: int, right: int, bottom: int) -> Image.Image:
    """Capture using PIL ImageGrab (slowest but most reliable)."""
    return ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)


def _capture_mss(left: int, top: int, right: int, bottom: int) -> Image.Image:
    """Capture using mss (fast, cross-platform)."""
    with mss_module.mss() as sct:
        monitor = {"left": left, "top": top, "width": right - left, "height": bottom - top}
        shot = sct.grab(monitor)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


def _capture_dxcam(left: int, top: int, right: int, bottom: int) -> Image.Image:
    """Capture using dxcam (fastest, GPU-accelerated, Windows only)."""
    camera = dxcam.create()
    frame = camera.grab(region=(left, top, right, bottom))
    if frame is None:
        raise RuntimeError("dxcam returned None frame")
    return Image.fromarray(frame)


def image_to_base64(image: Image.Image, max_width: int = 1920) -> str:
    """Convert PIL Image to base64-encoded JPEG data URL."""
    if image.width > max_width:
        ratio = max_width / image.width
        image = image.resize((max_width, int(image.height * ratio)), Image.LANCZOS)

    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"
```

- [ ] **Step 2: Implement screenshot MCP tools**

Create `src/windowsmcp_custom/tools/screenshot.py`:
```python
"""Screenshot and Snapshot MCP tools.

READ access: Can capture any/all screens (for pop-up detection).
Default: agent screen only.
"""

import logging
from fastmcp import Context

logger = logging.getLogger(__name__)


def register(mcp, *, get_display_manager, get_confinement):

    @mcp.tool(
        name="Screenshot",
        description=(
            "Take a screenshot of the agent's screen (default) or any/all screens.\n"
            "Returns a base64-encoded image.\n\n"
            "Parameters:\n"
            "- screen: 'agent' (default), 'all', or a screen index number"
        ),
    )
    def screenshot(screen: str = "agent", ctx: Context = None) -> list:
        dm = get_display_manager()
        ce = get_confinement()

        from windowsmcp_custom.display.capture import capture_region, image_to_base64

        if screen == "agent":
            bounds = ce.bounds
            if bounds is None:
                return ["No agent screen active. Call CreateScreen first."]
            image = capture_region(bounds.left, bounds.top, bounds.right, bounds.bottom)
            return [
                {"type": "image", "data": image_to_base64(image)},
                f"Screenshot of agent screen ({bounds.width}x{bounds.height})",
            ]

        elif screen == "all":
            monitors = dm.enumerate_monitors()
            results = []
            for m in monitors:
                image = capture_region(m.left, m.top, m.right, m.bottom)
                role = "[AGENT] " if m.is_agent else ""
                results.append({"type": "image", "data": image_to_base64(image)})
                results.append(f"{role}{m.device_name}: ({m.x},{m.y}) {m.width}x{m.height}")
            return results

        else:
            # Screen index
            try:
                idx = int(screen) - 1
                monitors = dm.enumerate_monitors()
                if 0 <= idx < len(monitors):
                    m = monitors[idx]
                    image = capture_region(m.left, m.top, m.right, m.bottom)
                    role = "[AGENT] " if m.is_agent else ""
                    return [
                        {"type": "image", "data": image_to_base64(image)},
                        f"{role}{m.device_name}: ({m.x},{m.y}) {m.width}x{m.height}",
                    ]
                else:
                    return [f"Screen index {screen} out of range. Use ScreenInfo to see available screens."]
            except ValueError:
                return [f"Invalid screen parameter: '{screen}'. Use 'agent', 'all', or a screen number."]

    @mcp.tool(
        name="Snapshot",
        description=(
            "Get a detailed snapshot of the agent's screen including interactive UI elements.\n"
            "Returns a screenshot plus a list of interactive elements with their positions.\n\n"
            "Parameters:\n"
            "- screen: 'agent' (default) or 'all'"
        ),
    )
    def snapshot(screen: str = "agent", ctx: Context = None) -> list:
        dm = get_display_manager()
        ce = get_confinement()

        from windowsmcp_custom.display.capture import capture_region, image_to_base64
        from windowsmcp_custom.uia.controls import (
            enumerate_windows, get_window_rect, get_window_title,
            get_window_class, is_window_visible,
        )

        bounds = ce.bounds
        if bounds is None and screen == "agent":
            return ["No agent screen active. Call CreateScreen first."]

        # Capture screenshot
        if screen == "agent" and bounds:
            image = capture_region(bounds.left, bounds.top, bounds.right, bounds.bottom)
        else:
            # Full virtual screen
            import ctypes
            vx = ctypes.windll.user32.GetSystemMetrics(76)
            vy = ctypes.windll.user32.GetSystemMetrics(77)
            vw = ctypes.windll.user32.GetSystemMetrics(78)
            vh = ctypes.windll.user32.GetSystemMetrics(79)
            image = capture_region(vx, vy, vx + vw, vy + vh)

        # Enumerate windows on target screen(s)
        elements = []
        for hwnd in enumerate_windows():
            if not is_window_visible(hwnd):
                continue
            rect = get_window_rect(hwnd)
            if rect is None:
                continue
            left, top, right, bottom = rect
            cx, cy = (left + right) // 2, (top + bottom) // 2

            on_agent = bounds and bounds.left <= cx < bounds.right and bounds.top <= cy < bounds.bottom

            if screen == "agent" and not on_agent:
                continue

            title = get_window_title(hwnd)
            if not title:
                continue

            # Convert to agent-relative coords if on agent screen
            if on_agent and bounds:
                rel_left = left - bounds.x
                rel_top = top - bounds.y
                rel_right = right - bounds.x
                rel_bottom = bottom - bounds.y
                screen_label = "[AGENT]"
            else:
                rel_left, rel_top, rel_right, rel_bottom = left, top, right, bottom
                screen_label = "[USER]"

            elements.append(
                f"  {screen_label} '{title}' "
                f"({rel_left},{rel_top})-({rel_right},{rel_bottom}) "
                f"class={get_window_class(hwnd)}"
            )

        results = [
            {"type": "image", "data": image_to_base64(image)},
            f"Windows on {'agent' if screen == 'agent' else 'all'} screen(s):\n"
            + "\n".join(elements[:30]),  # Cap at 30 entries
        ]
        return results
```

- [ ] **Step 3: Commit**

```bash
git add src/windowsmcp_custom/display/capture.py src/windowsmcp_custom/tools/screenshot.py
git commit -m "feat: screenshot tools and capture module with dxcam/mss/pillow fallback"
```

---

### Task 10: App Tool with Window Shepherd

**Files:**
- Create: `src/windowsmcp_custom/tools/app.py`

- [ ] **Step 1: Implement App tool**

Create `src/windowsmcp_custom/tools/app.py`:
```python
"""App MCP tool — launch applications and shepherd windows to agent screen."""

import subprocess
import time
import logging
import psutil
from fastmcp import Context

logger = logging.getLogger(__name__)


def register(mcp, *, get_display_manager, get_confinement):

    @mcp.tool(
        name="App",
        description=(
            "Launch an application on the agent's screen.\n"
            "The app window is automatically moved to the agent screen after launch.\n\n"
            "Parameters:\n"
            "- name: App name or full path (e.g. 'notepad', 'chrome', 'C:\\\\path\\\\app.exe')\n"
            "- args: Optional command line arguments\n"
            "- url: Optional URL to open (for browsers)"
        ),
    )
    def app(
        name: str,
        args: str | None = None,
        url: str | None = None,
        ctx: Context = None,
    ) -> str:
        dm = get_display_manager()
        agent = dm.agent_display
        if agent is None:
            return "No agent screen active. Call CreateScreen first."

        # Build command
        cmd = [name]
        if url:
            cmd.append(url)
        if args:
            cmd.extend(args.split())

        # Launch process
        try:
            proc = subprocess.Popen(
                cmd, shell=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            pid = proc.pid
        except Exception as e:
            return f"Failed to launch '{name}': {e}"

        # Window shepherd: watch for new windows from this process tree
        from windowsmcp_custom.uia.controls import (
            enumerate_windows, get_window_pid, get_window_rect,
            move_window, is_window_visible, get_window_title,
        )

        def get_process_tree_pids(root_pid: int) -> set[int]:
            """Get all PIDs in a process tree."""
            pids = {root_pid}
            try:
                parent = psutil.Process(root_pid)
                for child in parent.children(recursive=True):
                    pids.add(child.pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            return pids

        moved_handles = set()
        grace_end = time.time() + 5.0  # 5 second grace period
        first_title = None

        while time.time() < grace_end:
            pids = get_process_tree_pids(pid)

            for hwnd in enumerate_windows():
                if hwnd in moved_handles:
                    continue
                if not is_window_visible(hwnd):
                    continue
                if get_window_pid(hwnd) not in pids:
                    continue

                rect = get_window_rect(hwnd)
                if rect is None:
                    continue

                title = get_window_title(hwnd)
                if not title:
                    continue

                # Move window to agent screen
                w = rect[2] - rect[0]
                h = rect[3] - rect[1]
                # Position at top-left of agent screen, or maximize
                target_x = agent.x
                target_y = agent.y
                target_w = min(w, agent.width)
                target_h = min(h, agent.height)
                move_window(hwnd, target_x, target_y, target_w, target_h)
                moved_handles.add(hwnd)
                if first_title is None:
                    first_title = title
                logger.info(f"Shepherded window '{title}' to agent screen")

            if moved_handles:
                # Found at least one window, wait a bit more for splash/secondary windows
                time.sleep(0.2)
            else:
                time.sleep(0.1)

        if not moved_handles:
            return (
                f"Launched '{name}' (PID {pid}) but no windows appeared within 5 seconds. "
                "The app may still be loading. Use RecoverWindow to find it."
            )

        return f"Launched '{name}' — {len(moved_handles)} window(s) moved to agent screen. Main: '{first_title}'"
```

- [ ] **Step 2: Commit**

```bash
git add src/windowsmcp_custom/tools/app.py
git commit -m "feat: App tool with PID-tree window shepherd"
```

---

### Task 11: Pass-through Tools

**Files:**
- Create: `src/windowsmcp_custom/tools/shell.py`
- Create: `src/windowsmcp_custom/tools/filesystem.py`
- Create: `src/windowsmcp_custom/tools/clipboard.py`
- Create: `src/windowsmcp_custom/tools/process.py`
- Create: `src/windowsmcp_custom/tools/registry.py`
- Create: `src/windowsmcp_custom/tools/notification.py`
- Create: `src/windowsmcp_custom/tools/scrape.py`

These tools pass through without confinement. Each follows the same pattern.

- [ ] **Step 1: Implement all pass-through tools**

Create `src/windowsmcp_custom/tools/shell.py`:
```python
"""PowerShell MCP tool — unconfined, screen-independent."""

import subprocess
import logging
from fastmcp import Context

logger = logging.getLogger(__name__)


def register(mcp, *, get_display_manager, get_confinement):

    @mcp.tool(
        name="PowerShell",
        description=(
            "Execute a PowerShell command and return the output.\n\n"
            "Parameters:\n"
            "- command: PowerShell command to execute\n"
            "- timeout: Timeout in seconds (default 30, max 120)"
        ),
    )
    def powershell(command: str, timeout: int = 30, ctx: Context = None) -> str:
        timeout = max(1, min(120, timeout))
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True, text=True, timeout=timeout,
            )
            output = result.stdout
            if result.stderr:
                output += f"\n[STDERR]: {result.stderr}"
            if result.returncode != 0:
                output += f"\n[Exit code: {result.returncode}]"
            return output or "(no output)"
        except subprocess.TimeoutExpired:
            return f"Command timed out after {timeout}s"
        except Exception as e:
            return f"Failed to execute: {e}"
```

Create `src/windowsmcp_custom/tools/filesystem.py`:
```python
"""FileSystem MCP tool — unconfined, screen-independent."""

import os
import logging
from pathlib import Path
from fastmcp import Context

logger = logging.getLogger(__name__)


def register(mcp, *, get_display_manager, get_confinement):

    @mcp.tool(
        name="FileSystem",
        description=(
            "Perform file operations.\n\n"
            "Parameters:\n"
            "- action: 'read', 'write', 'list', 'info', 'delete', 'copy', 'move'\n"
            "- path: File or directory path\n"
            "- content: Content for write action\n"
            "- destination: Destination for copy/move"
        ),
    )
    def filesystem(
        action: str,
        path: str,
        content: str | None = None,
        destination: str | None = None,
        ctx: Context = None,
    ) -> str:
        p = Path(path)
        try:
            if action == "read":
                return p.read_text(encoding="utf-8", errors="replace")[:50000]
            elif action == "write":
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content or "", encoding="utf-8")
                return f"Written to {path}"
            elif action == "list":
                if not p.is_dir():
                    return f"Not a directory: {path}"
                entries = sorted(p.iterdir())[:100]
                return "\n".join(
                    f"{'[DIR]' if e.is_dir() else '[FILE]'} {e.name}" for e in entries
                )
            elif action == "info":
                stat = p.stat()
                return f"Path: {path}\nSize: {stat.st_size}\nIs dir: {p.is_dir()}"
            elif action == "delete":
                if p.is_dir():
                    import shutil
                    shutil.rmtree(p)
                else:
                    p.unlink()
                return f"Deleted: {path}"
            elif action in ("copy", "move"):
                if not destination:
                    return "Destination required for copy/move"
                import shutil
                if action == "copy":
                    if p.is_dir():
                        shutil.copytree(str(p), destination)
                    else:
                        shutil.copy2(str(p), destination)
                else:
                    shutil.move(str(p), destination)
                return f"{'Copied' if action == 'copy' else 'Moved'} to {destination}"
            else:
                return f"Unknown action: {action}"
        except Exception as e:
            return f"FileSystem error: {e}"
```

Create `src/windowsmcp_custom/tools/clipboard.py`:
```python
"""Clipboard MCP tool — unconfined, shared desktop clipboard."""

import logging
from fastmcp import Context

logger = logging.getLogger(__name__)


def register(mcp, *, get_display_manager, get_confinement):

    @mcp.tool(
        name="Clipboard",
        description="Get or set clipboard content.\n\nParameters:\n- action: 'get' or 'set'\n- content: Text to set (for 'set' action)",
    )
    def clipboard(action: str = "get", content: str | None = None, ctx: Context = None) -> str:
        import win32clipboard
        try:
            if action == "get":
                win32clipboard.OpenClipboard()
                try:
                    data = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
                    return data or "(clipboard empty)"
                except Exception:
                    return "(clipboard empty or non-text)"
                finally:
                    win32clipboard.CloseClipboard()
            elif action == "set":
                win32clipboard.OpenClipboard()
                try:
                    win32clipboard.EmptyClipboard()
                    win32clipboard.SetClipboardText(content or "", win32clipboard.CF_UNICODETEXT)
                    return "Clipboard set"
                finally:
                    win32clipboard.CloseClipboard()
            else:
                return f"Unknown action: {action}. Use 'get' or 'set'."
        except Exception as e:
            return f"Clipboard error: {e}"
```

Create `src/windowsmcp_custom/tools/process.py`:
```python
"""Process MCP tool — unconfined, screen-independent."""

import logging
import psutil
from fastmcp import Context

logger = logging.getLogger(__name__)


def register(mcp, *, get_display_manager, get_confinement):

    @mcp.tool(
        name="Process",
        description="List or terminate processes.\n\nParameters:\n- action: 'list' or 'kill'\n- name: Filter by process name (for list) or target (for kill)\n- pid: Process ID (for kill)",
    )
    def process(
        action: str = "list",
        name: str | None = None,
        pid: int | None = None,
        ctx: Context = None,
    ) -> str:
        if action == "list":
            procs = []
            for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
                try:
                    info = p.info
                    if name and name.lower() not in info["name"].lower():
                        continue
                    mem_mb = info["memory_info"].rss / 1024 / 1024 if info["memory_info"] else 0
                    procs.append(f"  PID {info['pid']:6d}  {info['name']:<30s}  {mem_mb:.1f}MB")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return f"Processes ({len(procs)}):\n" + "\n".join(procs[:50])
        elif action == "kill":
            if pid:
                try:
                    psutil.Process(pid).terminate()
                    return f"Terminated PID {pid}"
                except Exception as e:
                    return f"Failed to kill PID {pid}: {e}"
            elif name:
                killed = 0
                for p in psutil.process_iter(["pid", "name"]):
                    if p.info["name"].lower() == name.lower():
                        try:
                            p.terminate()
                            killed += 1
                        except Exception:
                            pass
                return f"Terminated {killed} process(es) named '{name}'"
            else:
                return "Provide pid or name to kill a process."
        else:
            return f"Unknown action: {action}"
```

Create `src/windowsmcp_custom/tools/registry.py`:
```python
"""Registry MCP tool — unconfined, screen-independent."""

import logging
import winreg
from fastmcp import Context

logger = logging.getLogger(__name__)

_HKEY_MAP = {
    "HKLM": winreg.HKEY_LOCAL_MACHINE,
    "HKCU": winreg.HKEY_CURRENT_USER,
    "HKCR": winreg.HKEY_CLASSES_ROOT,
    "HKU": winreg.HKEY_USERS,
}


def register(mcp, *, get_display_manager, get_confinement):

    @mcp.tool(
        name="Registry",
        description=(
            "Read or write Windows Registry values.\n\n"
            "Parameters:\n"
            "- action: 'read', 'write', or 'list'\n"
            "- key: Registry key path (e.g. 'HKCU\\\\Software\\\\MyApp')\n"
            "- name: Value name (for read/write)\n"
            "- value: Value data (for write)\n"
            "- value_type: 'REG_SZ' (default), 'REG_DWORD'"
        ),
    )
    def registry(
        action: str,
        key: str,
        name: str | None = None,
        value: str | None = None,
        value_type: str = "REG_SZ",
        ctx: Context = None,
    ) -> str:
        parts = key.split("\\", 1)
        if len(parts) != 2 or parts[0] not in _HKEY_MAP:
            return f"Invalid key format. Use HKLM\\\\path, HKCU\\\\path, etc."

        hkey_root = _HKEY_MAP[parts[0]]
        subkey = parts[1]

        try:
            if action == "read":
                with winreg.OpenKey(hkey_root, subkey) as k:
                    val, typ = winreg.QueryValueEx(k, name or "")
                    return f"{name or '(Default)'} = {val} (type={typ})"
            elif action == "list":
                with winreg.OpenKey(hkey_root, subkey) as k:
                    entries = []
                    i = 0
                    while True:
                        try:
                            vname, vdata, vtype = winreg.EnumValue(k, i)
                            entries.append(f"  {vname} = {vdata}")
                            i += 1
                        except OSError:
                            break
                    return f"Values in {key}:\n" + "\n".join(entries[:50])
            elif action == "write":
                reg_type = winreg.REG_SZ if value_type == "REG_SZ" else winreg.REG_DWORD
                write_val = int(value) if value_type == "REG_DWORD" else value
                with winreg.CreateKey(hkey_root, subkey) as k:
                    winreg.SetValueEx(k, name or "", 0, reg_type, write_val)
                    return f"Set {key}\\{name} = {value}"
            else:
                return f"Unknown action: {action}"
        except Exception as e:
            return f"Registry error: {e}"
```

Create `src/windowsmcp_custom/tools/notification.py`:
```python
"""Notification MCP tool — unconfined, screen-independent."""

import logging
from fastmcp import Context

logger = logging.getLogger(__name__)


def register(mcp, *, get_display_manager, get_confinement):

    @mcp.tool(
        name="Notification",
        description="Send a Windows toast notification.\n\nParameters:\n- title: Notification title\n- message: Notification body text",
    )
    def notification(title: str, message: str, ctx: Context = None) -> str:
        try:
            import subprocess
            ps_cmd = (
                f"[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
                f"ContentType = WindowsRuntime] | Out-Null; "
                f"$xml = [Windows.UI.Notifications.ToastNotificationManager]"
                f"::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02); "
                f"$texts = $xml.GetElementsByTagName('text'); "
                f"$texts[0].AppendChild($xml.CreateTextNode('{title.replace(chr(39), '')}')) | Out-Null; "
                f"$texts[1].AppendChild($xml.CreateTextNode('{message.replace(chr(39), '')}')) | Out-Null; "
                f"$toast = [Windows.UI.Notifications.ToastNotification]::new($xml); "
                f"[Windows.UI.Notifications.ToastNotificationManager]"
                f"::CreateToastNotifier('WindowsMCP').Show($toast)"
            )
            subprocess.run(["powershell", "-Command", ps_cmd], timeout=10, capture_output=True)
            return f"Notification sent: {title}"
        except Exception as e:
            return f"Notification failed: {e}"
```

Create `src/windowsmcp_custom/tools/scrape.py`:
```python
"""Scrape MCP tool — unconfined, web fetch only (no browser DOM extraction)."""

import logging
from fastmcp import Context

logger = logging.getLogger(__name__)


def register(mcp, *, get_display_manager, get_confinement):

    @mcp.tool(
        name="Scrape",
        description="Fetch web content from a URL. Returns the text content.\n\nParameters:\n- url: URL to fetch",
    )
    def scrape(url: str, ctx: Context = None) -> str:
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "WindowsMCP/0.1"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                content = resp.read().decode("utf-8", errors="replace")
                return content[:50000]
        except Exception as e:
            return f"Scrape failed: {e}"
```

- [ ] **Step 2: Commit**

```bash
git add src/windowsmcp_custom/tools/shell.py src/windowsmcp_custom/tools/filesystem.py \
  src/windowsmcp_custom/tools/clipboard.py src/windowsmcp_custom/tools/process.py \
  src/windowsmcp_custom/tools/registry.py src/windowsmcp_custom/tools/notification.py \
  src/windowsmcp_custom/tools/scrape.py
git commit -m "feat: pass-through tools — PowerShell, FileSystem, Clipboard, Process, Registry, Notification, Scrape"
```

---

### Task 12: Multi Tools

**Files:**
- Create: `src/windowsmcp_custom/tools/multi.py`

- [ ] **Step 1: Implement MultiSelect and MultiEdit**

Create `src/windowsmcp_custom/tools/multi.py`:
```python
"""MultiSelect and MultiEdit MCP tools — confined to agent screen."""

import time
import logging
from fastmcp import Context

from windowsmcp_custom.confinement.engine import ConfinementError

logger = logging.getLogger(__name__)


def register(mcp, *, get_display_manager, get_confinement):

    @mcp.tool(
        name="MultiSelect",
        description=(
            "Click multiple positions on the agent screen.\n\n"
            "Parameters:\n"
            "- positions: List of [x, y] coordinate pairs (agent-relative)\n"
            "- button: 'left' (default), 'right'"
        ),
    )
    def multi_select(
        positions: list[list[int]],
        button: str = "left",
        ctx: Context = None,
    ) -> str:
        ce = get_confinement()
        from windowsmcp_custom.uia.controls import click_at

        clicked = 0
        for pos in positions:
            if len(pos) < 2:
                continue
            try:
                abs_x, abs_y = ce.validate_and_translate(pos[0], pos[1])
                click_at(abs_x, abs_y, button=button)
                clicked += 1
                time.sleep(0.1)
            except ConfinementError as e:
                return f"MultiSelect stopped at position {clicked + 1}: {e}"

        return f"Clicked {clicked} positions"

    @mcp.tool(
        name="MultiEdit",
        description=(
            "Fill multiple input fields on the agent screen.\n\n"
            "Parameters:\n"
            "- fields: List of objects with 'x', 'y', and 'text' keys"
        ),
    )
    def multi_edit(
        fields: list[dict],
        ctx: Context = None,
    ) -> str:
        ce = get_confinement()
        from windowsmcp_custom.uia.controls import click_at, type_text

        filled = 0
        for field in fields:
            x = field.get("x")
            y = field.get("y")
            text = field.get("text", "")
            if x is None or y is None:
                continue
            try:
                abs_x, abs_y = ce.validate_and_translate(x, y)
                click_at(abs_x, abs_y)
                time.sleep(0.1)
                type_text(text)
                filled += 1
                time.sleep(0.1)
            except ConfinementError as e:
                return f"MultiEdit stopped at field {filled + 1}: {e}"

        return f"Filled {filled} fields"
```

- [ ] **Step 2: Commit**

```bash
git add src/windowsmcp_custom/tools/multi.py
git commit -m "feat: MultiSelect and MultiEdit tools with confinement"
```

---

### Task 13: State Machine

**Files:**
- Create: `src/windowsmcp_custom/server.py`

- [ ] **Step 1: Implement server state machine**

Create `src/windowsmcp_custom/server.py`:
```python
"""Server state machine and lifecycle management."""

import logging
from enum import Enum

logger = logging.getLogger(__name__)


class ServerState(Enum):
    INIT = "init"
    DRIVER_MISSING = "driver_missing"
    CREATING_DISPLAY = "creating_display"
    CREATE_FAILED = "create_failed"
    READY = "ready"
    DEGRADED = "degraded"
    RECOVERING = "recovering"
    SHUTTING_DOWN = "shutting_down"


class ServerStateManager:
    """Manages the server's lifecycle state."""

    def __init__(self):
        self._state = ServerState.INIT
        self._state_listeners: list[callable] = []
        self._degraded_reason: str | None = None

    @property
    def state(self) -> ServerState:
        return self._state

    @property
    def is_gui_available(self) -> bool:
        """Whether GUI tools (read + write) are available."""
        return self._state in (ServerState.READY, ServerState.DEGRADED)

    @property
    def is_gui_write_available(self) -> bool:
        """Whether GUI write tools are available."""
        return self._state == ServerState.READY

    @property
    def is_unconfined_available(self) -> bool:
        """Whether unconfined tools are available."""
        return self._state not in (ServerState.INIT, ServerState.SHUTTING_DOWN)

    def transition(self, new_state: ServerState, reason: str | None = None):
        """Transition to a new state."""
        old = self._state
        self._state = new_state
        self._degraded_reason = reason if new_state == ServerState.DEGRADED else None
        logger.info(f"State: {old.value} → {new_state.value}" + (f" ({reason})" if reason else ""))
        for listener in self._state_listeners:
            try:
                listener(old, new_state, reason)
            except Exception:
                logger.exception("Error in state listener")

    def add_listener(self, callback: callable):
        """Add a state change listener."""
        self._state_listeners.append(callback)

    def get_status(self) -> dict:
        """Get current status as a dict (for IPC publishing)."""
        return {
            "state": self._state.value,
            "gui_available": self.is_gui_available,
            "gui_write_available": self.is_gui_write_available,
            "degraded_reason": self._degraded_reason,
        }
```

- [ ] **Step 2: Commit**

```bash
git add src/windowsmcp_custom/server.py
git commit -m "feat: server state machine with lifecycle transitions"
```

---

### Task 14: Server Integration — Wire Everything Together

**Files:**
- Modify: `src/windowsmcp_custom/__main__.py`
- Modify: `src/windowsmcp_custom/tools/__init__.py`

- [ ] **Step 1: Update entry point to integrate all components**

Rewrite `src/windowsmcp_custom/__main__.py`:
```python
"""Entry point for the WindowsMCP Custom server."""

import asyncio
import logging
import click
from fastmcp import FastMCP
from contextlib import asynccontextmanager

from windowsmcp_custom.display.manager import DisplayManager
from windowsmcp_custom.confinement.engine import ConfinementEngine
from windowsmcp_custom.confinement.bounds import DisplayChangeListener
from windowsmcp_custom.server import ServerStateManager, ServerState
from windowsmcp_custom.tools import register_all

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Global state
display_manager: DisplayManager | None = None
confinement: ConfinementEngine | None = None
state_manager: ServerStateManager | None = None
display_listener: DisplayChangeListener | None = None


@asynccontextmanager
async def lifespan(app: FastMCP):
    """Initialize and clean up server components."""
    global display_manager, confinement, state_manager, display_listener

    state_manager = ServerStateManager()
    display_manager = DisplayManager()
    confinement = ConfinementEngine()

    # Check driver availability
    if display_manager.check_driver():
        state_manager.transition(ServerState.READY)
        logger.info("Parsec VDD driver found. Ready for CreateScreen.")
    else:
        state_manager.transition(ServerState.DRIVER_MISSING)
        logger.warning(
            "Parsec VDD driver not found. Install it from https://github.com/nomi-san/parsec-vdd. "
            "Non-GUI tools are still available."
        )

    # Start display change listener
    def on_display_change():
        if display_manager and display_manager.is_ready:
            display_manager.refresh_bounds()
            if display_manager.agent_display:
                confinement.set_agent_bounds(display_manager.agent_display)
            else:
                confinement.clear_bounds()
                state_manager.transition(ServerState.DEGRADED, "agent display lost")

    def on_session_change(event_type):
        from windowsmcp_custom.confinement.bounds import WTS_SESSION_LOCK, WTS_SESSION_UNLOCK
        if event_type == WTS_SESSION_LOCK:
            state_manager.transition(ServerState.DEGRADED, "session locked")
        elif event_type == WTS_SESSION_UNLOCK:
            if display_manager.is_ready:
                display_manager.refresh_bounds()
                state_manager.transition(ServerState.READY)

    display_listener = DisplayChangeListener(
        on_display_change=on_display_change,
        on_session_change=on_session_change,
    )
    display_listener.start()

    try:
        yield
    finally:
        state_manager.transition(ServerState.SHUTTING_DOWN)
        if display_listener:
            display_listener.stop()
        if display_manager and display_manager.is_ready:
            display_manager.destroy_display()
        logger.info("Server shut down")


mcp = FastMCP(
    name="windowsmcp-custom",
    instructions=(
        "WindowsMCP Custom provides tools to interact with a confined virtual display. "
        "The agent operates on a dedicated virtual screen and cannot interact with the "
        "user's physical screens via GUI tools.\n\n"
        "IMPORTANT: Call CreateScreen first to set up your virtual display before using "
        "any GUI tools (Screenshot, Click, Type, etc.).\n\n"
        "Your screen coordinates are relative: (0,0) is top-left of your screen.\n"
        "If a dialog appears on the wrong screen, use Screenshot with screen='all' "
        "to find it, then RecoverWindow to move it to your screen."
    ),
    lifespan=lifespan,
)


def _get_display_manager():
    return display_manager


def _get_confinement():
    return confinement


register_all(mcp, get_display_manager=_get_display_manager, get_confinement=_get_confinement)


@click.command()
@click.option("--transport", type=click.Choice(["stdio", "sse"]), default="stdio")
@click.option("--host", default="localhost", type=str)
@click.option("--port", default=8000, type=int)
def main(transport: str, host: str, port: int):
    """Start the WindowsMCP Custom server."""
    mcp.run(transport=transport, host=host, port=port, show_banner=False)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the server to verify startup**

```bash
uv run python -c "
from windowsmcp_custom.__main__ import mcp
print(f'Server: {mcp.name}')
print(f'Tools registered: {len(mcp._tool_manager._tools)}')
for name in sorted(mcp._tool_manager._tools.keys()):
    print(f'  - {name}')
"
```

Expected: Server name + list of all 20 tools.

- [ ] **Step 3: Commit**

```bash
git add src/windowsmcp_custom/__main__.py
git commit -m "feat: wire all components together — server integration"
```

---

### Task 15: IPC Layer (Stub for UI Communication)

**Files:**
- Create: `src/windowsmcp_custom/ipc/__init__.py`
- Create: `src/windowsmcp_custom/ipc/status.py`
- Create: `src/windowsmcp_custom/ipc/frames.py`
- Create: `src/windowsmcp_custom/ipc/commands.py`

- [ ] **Step 1: Implement IPC stubs**

Create `src/windowsmcp_custom/ipc/__init__.py`:
```python
"""IPC layer for communication between MCP server and Management UI."""
```

Create `src/windowsmcp_custom/ipc/status.py`:
```python
"""Named pipe server for publishing status updates to the UI."""

import json
import logging
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

STATUS_FILE = Path.home() / ".windowsmcp" / "status.json"


class StatusPublisher:
    """Publishes server status to a file for the UI to read.

    Uses a simple file-based approach for the initial implementation.
    Can be upgraded to named pipes later.
    """

    def __init__(self, get_status):
        self._get_status = get_status
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self):
        STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        self._running = True
        self._thread = threading.Thread(target=self._publish_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        if STATUS_FILE.exists():
            STATUS_FILE.unlink(missing_ok=True)

    def _publish_loop(self):
        while self._running:
            try:
                status = self._get_status()
                STATUS_FILE.write_text(json.dumps(status, indent=2))
            except Exception:
                pass
            time.sleep(1.0)
```

Create `src/windowsmcp_custom/ipc/frames.py`:
```python
"""Shared memory frame buffer for delivering screenshots to the UI viewer.

Initial implementation: file-based frame delivery.
Can be upgraded to mmap shared memory later.
"""

import logging

logger = logging.getLogger(__name__)


class FrameBuffer:
    """Placeholder for frame delivery to the viewer UI.

    Will be implemented when the Management UI is built.
    """

    def __init__(self):
        self._latest_frame = None

    def push_frame(self, frame_data: bytes, width: int, height: int):
        self._latest_frame = (frame_data, width, height)

    def get_frame(self):
        return self._latest_frame
```

Create `src/windowsmcp_custom/ipc/commands.py`:
```python
"""Named pipe command receiver for UI → Server communication.

Initial implementation: stub.
"""

import logging

logger = logging.getLogger(__name__)


class CommandReceiver:
    """Placeholder for receiving commands from the Management UI.

    Will be implemented when the Management UI is built.
    """

    def __init__(self):
        pass

    def start(self):
        pass

    def stop(self):
        pass
```

- [ ] **Step 2: Commit**

```bash
git add src/windowsmcp_custom/ipc/
git commit -m "feat: IPC layer stubs — status publisher, frame buffer, command receiver"
```

---

### Task 16: Management UI (Toolbar + Viewer)

**Files:**
- Create: `ui/__init__.py`
- Create: `ui/main.py`
- Create: `ui/toolbar.py`
- Create: `ui/viewer.py`

- [ ] **Step 1: Implement Management UI**

Create `ui/__init__.py` (empty file).

Create `ui/main.py`:
```python
"""Management UI entry point — launches toolbar and viewer."""

import sys
import json
import logging
from pathlib import Path

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

from ui.toolbar import ToolbarWindow

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STATUS_FILE = Path.home() / ".windowsmcp" / "status.json"


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("WindowsMCP Custom")

    toolbar = ToolbarWindow()
    toolbar.show()

    # Poll status file
    def update_status():
        try:
            if STATUS_FILE.exists():
                status = json.loads(STATUS_FILE.read_text())
                toolbar.update_status(status)
        except Exception:
            pass

    timer = QTimer()
    timer.timeout.connect(update_status)
    timer.start(1000)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
```

Create `ui/toolbar.py`:
```python
"""Floating toolbar widget — always-on-top control panel."""

import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont

logger = logging.getLogger(__name__)


class ToolbarWindow(QWidget):
    """Compact floating toolbar for managing the agent's virtual display."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("WindowsMCP")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setFixedWidth(240)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._dragging = False
        self._drag_pos = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Container with background
        container = QFrame()
        container.setStyleSheet("""
            QFrame {
                background-color: #1a1a2e;
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 10px;
            }
        """)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(12, 8, 12, 8)
        container_layout.setSpacing(8)

        # Title bar
        title_row = QHBoxLayout()
        self._status_dot = QLabel("●")
        self._status_dot.setStyleSheet("color: #6b7280; font-size: 10px;")
        title_label = QLabel("WindowsMCP")
        title_label.setStyleSheet("color: #e6edf3; font-size: 12px; font-weight: bold;")
        title_row.addWidget(self._status_dot)
        title_row.addWidget(title_label)
        title_row.addStretch()
        container_layout.addLayout(title_row)

        # Status labels
        self._state_label = QLabel("State: init")
        self._state_label.setStyleSheet("color: #9ca3af; font-size: 11px;")
        container_layout.addWidget(self._state_label)

        self._screen_label = QLabel("Screen: none")
        self._screen_label.setStyleSheet("color: #9ca3af; font-size: 11px;")
        container_layout.addWidget(self._screen_label)

        # Buttons
        btn_row = QHBoxLayout()
        self._viewer_btn = QPushButton("Open Viewer")
        self._viewer_btn.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6; color: white;
                border: none; border-radius: 4px;
                padding: 6px; font-size: 11px; font-weight: bold;
            }
            QPushButton:hover { background-color: #2563eb; }
        """)
        self._viewer_btn.clicked.connect(self._open_viewer)
        btn_row.addWidget(self._viewer_btn)
        container_layout.addLayout(btn_row)

        layout.addWidget(container)

    def update_status(self, status: dict):
        state = status.get("state", "unknown")
        self._state_label.setText(f"State: {state}")

        if state == "ready":
            self._status_dot.setStyleSheet("color: #10b981; font-size: 10px;")
        elif state in ("degraded", "driver_missing"):
            self._status_dot.setStyleSheet("color: #f59e0b; font-size: 10px;")
        else:
            self._status_dot.setStyleSheet("color: #6b7280; font-size: 10px;")

    def _open_viewer(self):
        from ui.viewer import ViewerWindow
        if not hasattr(self, '_viewer') or self._viewer is None:
            self._viewer = ViewerWindow()
        self._viewer.show()
        self._viewer.raise_()

    # Draggable window support
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_pos = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if self._dragging and self._drag_pos:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._dragging = False
```

Create `ui/viewer.py`:
```python
"""Interactive viewer window — shows live feed of agent's virtual display."""

import logging
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout, QPushButton
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap

logger = logging.getLogger(__name__)


class ViewerWindow(QWidget):
    """Resizable viewer showing the agent's virtual screen."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Agent Screen Viewer")
        self.resize(960, 540)
        self._setup_ui()

        # Capture timer
        self._timer = QTimer()
        self._timer.timeout.connect(self._capture_frame)
        self._timer.start(33)  # ~30fps

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(8, 4, 8, 4)
        title = QLabel("Agent Screen Viewer")
        title.setStyleSheet("font-weight: bold; font-size: 12px;")
        self._live_label = QLabel("LIVE")
        self._live_label.setStyleSheet(
            "color: #10b981; background: rgba(16,185,129,0.2); "
            "padding: 2px 6px; border-radius: 3px; font-size: 9px;"
        )
        toolbar.addWidget(title)
        toolbar.addWidget(self._live_label)
        toolbar.addStretch()

        fullscreen_btn = QPushButton("Fullscreen")
        fullscreen_btn.clicked.connect(self._toggle_fullscreen)
        fullscreen_btn.setStyleSheet("font-size: 10px; padding: 2px 8px;")
        toolbar.addWidget(fullscreen_btn)

        toolbar_widget = QWidget()
        toolbar_widget.setLayout(toolbar)
        toolbar_widget.setStyleSheet("background: #16162a;")
        layout.addWidget(toolbar_widget)

        # Display area
        self._display = QLabel()
        self._display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._display.setStyleSheet("background: #0d1117;")
        self._display.setMinimumSize(640, 360)
        self._display.setText("Waiting for agent screen...")
        layout.addWidget(self._display, stretch=1)

    def _capture_frame(self):
        """Capture the agent's virtual display and show it."""
        try:
            from windowsmcp_custom.display.identity import load_state
            from windowsmcp_custom.display.capture import capture_region
            import json
            from pathlib import Path

            status_file = Path.home() / ".windowsmcp" / "status.json"
            if not status_file.exists():
                return

            status = json.loads(status_file.read_text())
            if status.get("state") != "ready":
                return

            state = load_state()
            if not state:
                return

            # We need the actual bounds — read from display enumeration
            # For now, capture based on stored info
            # This will be replaced with proper IPC frame delivery
            import win32api
            monitors = win32api.EnumDisplayMonitors(None, None)
            for _hMon, _hdc, rect in monitors:
                left, top, right, bottom = rect
                w, h = right - left, bottom - top
                if w == state.width and h == state.height:
                    image = capture_region(left, top, right, bottom)
                    # Convert PIL to QPixmap
                    data = image.tobytes("raw", "RGB")
                    qimg = QImage(data, image.width, image.height, QImage.Format.Format_RGB888)
                    pixmap = QPixmap.fromImage(qimg)
                    scaled = pixmap.scaled(
                        self._display.size(),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    self._display.setPixmap(scaled)
                    break
        except Exception as e:
            logger.debug(f"Frame capture failed: {e}")

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    # Interactive: forward mouse events
    def mousePressEvent(self, event):
        # TODO: Translate click position to agent screen coords and inject
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and self.isFullScreen():
            self.showNormal()
        # TODO: Forward keyboard to agent screen
        super().keyPressEvent(event)
```

- [ ] **Step 2: Commit**

```bash
git add ui/
git commit -m "feat: management UI — floating toolbar + interactive viewer"
```

---

### Task 17: E2E Integration — Register with Claude Code

**Files:**
- Modify: Claude Code MCP settings

- [ ] **Step 1: Test the server starts and lists tools**

```bash
cd C:/Users/doubi/Claude_Project/WindowsMCP_Custom
uv run windowsmcp-custom --transport stdio
```

Press Ctrl+C to stop. Verify it starts without errors.

- [ ] **Step 2: Register as Claude Code MCP server**

Run this to add the MCP server to Claude Code settings:

```bash
claude mcp add windowsmcp-custom -- uv run --directory "C:/Users/doubi/Claude_Project/WindowsMCP_Custom" windowsmcp-custom
```

- [ ] **Step 3: Verify MCP registration**

```bash
claude mcp list
```

Expected: `windowsmcp-custom` appears in the list.

- [ ] **Step 4: Test E2E with Claude Code**

Start a new Claude Code session and test:

1. Ask Claude to call `ScreenInfo` — should list physical monitors
2. Ask Claude to call `CreateScreen` — should create virtual display (requires Parsec VDD installed)
3. Ask Claude to call `Screenshot` — should capture the agent screen
4. Ask Claude to call `App` with `name=notepad` — should launch Notepad on agent screen
5. Ask Claude to call `Click` with coordinates — should click on agent screen
6. Ask Claude to call `DestroyScreen` — should clean up

- [ ] **Step 5: Push to GitHub**

```bash
cd C:/Users/doubi/Claude_Project/WindowsMCP_Custom
git push origin master
```

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "feat: E2E integration — Claude Code MCP registration"
```

---

## Post-MVP Tasks (Future)

These are not part of this plan but noted for future work:

1. **IPC upgrade** — Replace file-based status/frames with named pipes and shared memory
2. **Viewer input forwarding** — Forward mouse/keyboard from viewer to agent screen
3. **Action overlay** — Show agent's last action in the viewer
4. **State machine refinements** — DEGRADED sub-states, capability matrix
5. **Topology change hardening** — Abort in-flight actions on WM_DISPLAYCHANGE
6. **Elevated app detection** — UIPI check before input injection
7. **Window shepherd improvements** — Event-driven with configurable grace period
