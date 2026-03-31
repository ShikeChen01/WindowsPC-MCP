"""Desktop isolation for the agent — create, switch, and destroy Win32 desktops."""

from .controller import DesktopController
from .gate import InputGate, InputMode
from .hotkeys import HotkeyError, HotkeyId, HotkeyService
from .manager import DesktopError, DesktopManager

__all__ = [
    "DesktopController",
    "DesktopError",
    "DesktopManager",
    "HotkeyError",
    "HotkeyId",
    "HotkeyService",
    "InputGate",
    "InputMode",
]
