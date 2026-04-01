"""Core confinement logic for restricting agent GUI actions to the virtual display."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import Enum
from typing import Any

from windowspc_mcp.confinement.errors import ConfinementError  # re-export


class ActionType(Enum):
    READ = "read"
    WRITE = "write"
    UNCONFINED = "unconfined"


@dataclass(frozen=True)
class ScreenBounds:
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


_TOOL_ACTIONS: dict[str, ActionType] = {
    # READ tools
    "Screenshot": ActionType.READ,
    "Snapshot": ActionType.READ,
    "Scrape": ActionType.READ,
    "ScreenInfo": ActionType.READ,
    # WRITE tools
    "Click": ActionType.WRITE,
    "Type": ActionType.WRITE,
    "Move": ActionType.WRITE,
    "Scroll": ActionType.WRITE,
    "Shortcut": ActionType.WRITE,
    "App": ActionType.WRITE,
    "MultiSelect": ActionType.WRITE,
    "MultiEdit": ActionType.WRITE,
    "RecoverWindow": ActionType.WRITE,
    # UNCONFINED tools
    "Wait": ActionType.UNCONFINED,
    "Notification": ActionType.UNCONFINED,
    "PowerShell": ActionType.UNCONFINED,
    "FileSystem": ActionType.UNCONFINED,
    "Clipboard": ActionType.UNCONFINED,
    "Process": ActionType.UNCONFINED,
    "Registry": ActionType.UNCONFINED,
    "CreateScreen": ActionType.UNCONFINED,
    "DestroyScreen": ActionType.UNCONFINED,
}


class ConfinementEngine:
    """Engine that validates and translates GUI actions to stay within agent screen bounds."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._bounds: ScreenBounds | None = None

    @property
    def bounds(self) -> ScreenBounds | None:
        return self._bounds

    def set_agent_bounds(self, bounds: Any) -> None:
        """Accept any object with x, y, width, height attributes."""
        x, y, w, h = bounds.x, bounds.y, bounds.width, bounds.height
        if w <= 0 or h <= 0:
            raise ConfinementError(f"Invalid bounds: width={w}, height={h} must be positive")
        with self._lock:
            self._bounds = ScreenBounds(x=x, y=y, width=w, height=h)

    def clear_bounds(self) -> None:
        with self._lock:
            self._bounds = None

    def classify_action(self, tool_name: str) -> ActionType:
        """Return the ActionType for the given tool name.

        Raises:
            ConfinementError: If tool_name is not registered (fail-closed).
        """
        try:
            return _TOOL_ACTIONS[tool_name]
        except KeyError:
            raise ConfinementError(f"Unknown tool: {tool_name!r}")

    def validate_and_translate(self, rel_x: int, rel_y: int) -> tuple[int, int]:
        """Validate relative coordinates and translate to absolute screen coordinates.

        Args:
            rel_x: X coordinate relative to the agent's virtual display (0-based).
            rel_y: Y coordinate relative to the agent's virtual display (0-based).

        Returns:
            (abs_x, abs_y) absolute screen coordinates.

        Raises:
            ConfinementError: If no agent display is set, or coordinates are out of bounds.
        """
        with self._lock:
            if self._bounds is None:
                raise ConfinementError(
                    "no agent display assigned — call set_agent_bounds() before translating coordinates"
                )

            bounds = self._bounds
            if rel_x < 0 or rel_x >= bounds.width or rel_y < 0 or rel_y >= bounds.height:
                raise ConfinementError(
                    f"coordinate ({rel_x}, {rel_y}) is out of bounds for agent display "
                    f"{bounds.width}x{bounds.height} — "
                    f"valid range is x=[0, {bounds.width - 1}], y=[0, {bounds.height - 1}]"
                )

            return (rel_x + bounds.x, rel_y + bounds.y)

    def is_point_on_agent_screen(self, abs_x: int, abs_y: int) -> bool:
        """Return True if the absolute point lies within the agent's screen bounds."""
        with self._lock:
            if self._bounds is None:
                return False
            b = self._bounds
            return b.left <= abs_x < b.right and b.top <= abs_y < b.bottom

    def validate_absolute_point(self, abs_x: int, abs_y: int) -> None:
        """Raise ConfinementError if the absolute point is not on the agent screen."""
        with self._lock:
            if self._bounds is None:
                raise ConfinementError(
                    "no agent display assigned — cannot validate absolute point"
                )
            b = self._bounds
            if not (b.left <= abs_x < b.right and b.top <= abs_y < b.bottom):
                raise ConfinementError(
                    f"absolute point ({abs_x}, {abs_y}) is not on the agent screen "
                    f"[{b.left}, {b.top}) to ({b.right}, {b.bottom})"
                )
