"""Desktop isolation for the agent — create, switch, and destroy Win32 desktops."""

from .manager import DesktopError, DesktopManager

__all__ = [
    "DesktopError",
    "DesktopManager",
]
