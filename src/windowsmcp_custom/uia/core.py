"""UIAutomation COM singleton and SendInput Win32 structures."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import time
from ctypes import POINTER, Structure, Union, c_long, c_ulong, c_ushort, c_wchar_p

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Win32 API return type declarations
# ---------------------------------------------------------------------------

user32 = ctypes.windll.user32

user32.GetForegroundWindow.restype = ctypes.wintypes.HWND
user32.GetForegroundWindow.argtypes = []

user32.GetAncestor.restype = ctypes.wintypes.HWND
user32.GetAncestor.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.UINT]

user32.SetForegroundWindow.restype = ctypes.wintypes.BOOL
user32.SetForegroundWindow.argtypes = [ctypes.wintypes.HWND]

user32.SetCursorPos.restype = ctypes.wintypes.BOOL
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]

user32.GetCursorPos.restype = ctypes.wintypes.BOOL
user32.GetCursorPos.argtypes = [POINTER(ctypes.wintypes.POINT)]

user32.GetWindowRect.restype = ctypes.wintypes.BOOL
user32.GetWindowRect.argtypes = [ctypes.wintypes.HWND, POINTER(ctypes.wintypes.RECT)]

user32.MoveWindow.restype = ctypes.wintypes.BOOL
user32.MoveWindow.argtypes = [
    ctypes.wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.wintypes.BOOL,
]

user32.IsWindowVisible.restype = ctypes.wintypes.BOOL
user32.IsWindowVisible.argtypes = [ctypes.wintypes.HWND]

user32.GetWindowThreadProcessId.restype = ctypes.wintypes.DWORD
user32.GetWindowThreadProcessId.argtypes = [
    ctypes.wintypes.HWND,
    POINTER(ctypes.wintypes.DWORD),
]

user32.ShowWindow.restype = ctypes.wintypes.BOOL
user32.ShowWindow.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]

# EnumWindowsProc callback type
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
user32.EnumWindows.restype = ctypes.wintypes.BOOL
user32.EnumWindows.argtypes = [WNDENUMPROC, ctypes.wintypes.LPARAM]

user32.GetClassNameW.restype = ctypes.c_int
user32.GetClassNameW.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.LPWSTR, ctypes.c_int]

user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.LPWSTR, ctypes.c_int]

user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextLengthW.argtypes = [ctypes.wintypes.HWND]

# ---------------------------------------------------------------------------
# SendInput structures
# ---------------------------------------------------------------------------

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

# Window constants
SW_RESTORE = 9
GA_ROOT = 2


class MOUSEINPUT(Structure):
    _fields_ = [
        ("dx", c_long),
        ("dy", c_long),
        ("mouseData", c_ulong),
        ("dwFlags", c_ulong),
        ("time", c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class KEYBDINPUT(Structure):
    _fields_ = [
        ("wVk", c_ushort),
        ("wScan", c_ushort),
        ("dwFlags", c_ulong),
        ("time", c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class INPUT_UNION(Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
    ]


class INPUT(Structure):
    _fields_ = [
        ("type", c_ulong),
        ("_input", INPUT_UNION),
    ]


user32.SendInput.restype = ctypes.c_uint
user32.SendInput.argtypes = [ctypes.c_uint, POINTER(INPUT), ctypes.c_int]


def send_input(*inputs: INPUT) -> int:
    """Send a sequence of INPUT structures via SendInput."""
    n = len(inputs)
    arr = (INPUT * n)(*inputs)
    return user32.SendInput(n, arr, ctypes.sizeof(INPUT))


# ---------------------------------------------------------------------------
# _AutomationClient — UIAutomation COM singleton
# ---------------------------------------------------------------------------

class _AutomationClient:
    """Singleton COM client wrapping IUIAutomation."""

    _instance: "_AutomationClient | None" = None

    def __new__(cls) -> "_AutomationClient":
        if cls._instance is None:
            obj = super().__new__(cls)
            obj._initialized = False
            cls._instance = obj
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._uia = None
        self._walker = None
        self._init_com()
        self._initialized = True

    def _init_com(self) -> None:
        import comtypes
        import comtypes.client

        for attempt in range(3):
            try:
                comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
            except OSError:
                pass  # already initialized on this thread

            try:
                # Load UIAutomationCore.dll via comtypes
                uia_dll = comtypes.client.GetModule("UIAutomationCore.dll")
                self._uia = comtypes.client.CreateObject(
                    uia_dll.CUIAutomation,
                    interface=uia_dll.IUIAutomation,
                )
                self._walker = self._uia.RawViewWalker
                log.debug("UIAutomation COM client initialized (attempt %d)", attempt + 1)
                return
            except Exception as exc:
                log.warning("UIAutomation init attempt %d failed: %s", attempt + 1, exc)
                if attempt < 2:
                    time.sleep(0.5 * (attempt + 1))

        log.error("UIAutomation COM client could not be initialized after 3 attempts")

    @property
    def uia(self):
        """Return the IUIAutomation interface, re-initializing if needed."""
        if self._uia is None:
            self._init_com()
        return self._uia

    @property
    def walker(self):
        """Return the RawViewWalker, re-initializing if needed."""
        if self._walker is None:
            self._init_com()
        return self._walker


# Module-level singleton accessor
def get_automation_client() -> _AutomationClient:
    """Return the module-level UIAutomation singleton."""
    return _AutomationClient()
