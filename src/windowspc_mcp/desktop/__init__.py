"""Desktop isolation for the agent — create, switch, and destroy Win32 desktops."""

from .hotkeys import HotkeyError, HotkeyId, HotkeyService
from .manager import DesktopError, DesktopManager

__all__ = [
    "DesktopError",
    "DesktopManager",
    "HotkeyError",
    "HotkeyId",
    "HotkeyService",
]
