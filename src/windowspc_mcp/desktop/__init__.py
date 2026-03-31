"""Desktop isolation for the agent — create, switch, and destroy Win32 desktops."""

from .controller import DesktopController
from .gate import InputGate, InputMode
from .hotkeys import HotkeyError, HotkeyId, HotkeyService
from .manager import DesktopError, DesktopManager
from .responses import format_gate_error

__all__ = [
    "DesktopController",
    "DesktopError",
    "DesktopManager",
    "HotkeyError",
    "HotkeyId",
    "HotkeyService",
    "InputGate",
    "InputMode",
    "format_gate_error",
]
