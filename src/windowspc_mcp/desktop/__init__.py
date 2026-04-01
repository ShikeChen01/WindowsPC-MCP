"""Desktop isolation for the agent — create, switch, and destroy Win32 desktops."""

from .capture import DesktopCapture, FrameBuffer
from .controller import DesktopController
from .gate import InputGate, InputMode
from .hotkeys import HotkeyError, HotkeyId, HotkeyService
from .manager import DesktopError, DesktopManager
from .monitor import InputDecayMonitor
from .overlay import ConflictDetector, CursorState, GhostCursorOverlay
from .profiler import ActionProfiler, ActionTiming, InputActionType
from .responses import format_gate_error
from .scheduler import CursorScheduler, Instruction
from .viewer import ViewerWindow

__all__ = [
    "ActionProfiler",
    "ActionTiming",
    "InputActionType",
    "ConflictDetector",
    "CursorScheduler",
    "CursorState",
    "DesktopCapture",
    "DesktopController",
    "DesktopError",
    "DesktopManager",
    "FrameBuffer",
    "GhostCursorOverlay",
    "HotkeyError",
    "HotkeyId",
    "HotkeyService",
    "InputDecayMonitor",
    "InputGate",
    "InputMode",
    "Instruction",
    "ViewerWindow",
    "format_gate_error",
]
