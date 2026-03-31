"""InputGate — mode-based routing for agent input operations.

Central routing layer that checks the current operating mode and decides
whether agent input should proceed, queue, or be rejected.  Thread-safe;
mode can be changed from any thread (e.g. the hotkey listener) while MCP
tool threads call :meth:`check`.
"""

from __future__ import annotations

import logging
import threading
from enum import Enum
from typing import Callable

from windowspc_mcp.confinement.errors import (
    AgentPaused,
    AgentPreempted,
    EmergencyStop,
    InvalidStateError,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Operating modes
# ---------------------------------------------------------------------------


class InputMode(Enum):
    """Operating modes for the agent input pipeline."""

    AGENT_SOLO = "agent_solo"          # Agent desktop is input desktop, full speed
    COWORK = "cowork"                  # Shared desktop, scheduled via CursorScheduler
    HUMAN_OVERRIDE = "human_override"  # Human took control, agent blocked
    HUMAN_HOME = "human_home"          # User's desktop active, agent paused
    EMERGENCY_STOP = "emergency_stop"  # Session terminated


# ---------------------------------------------------------------------------
# InputGate
# ---------------------------------------------------------------------------


class InputGate:
    """Gate that every agent input operation must pass through.

    Call :meth:`check` before performing any input.  The gate inspects the
    current :class:`InputMode` and either returns immediately (allowing the
    operation) or raises an appropriate exception to block it.
    """

    def __init__(self) -> None:
        """Initialize in HUMAN_HOME mode (safe default)."""
        self._lock = threading.Lock()
        self._mode: InputMode = InputMode.HUMAN_HOME
        self._listeners: list[Callable[[InputMode, InputMode], None]] = []

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def mode(self) -> InputMode:
        """Current operating mode."""
        return self._mode

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_mode(self, mode: InputMode) -> None:
        """Transition to a new mode.  Thread-safe.

        Notifies any registered listeners synchronously in the calling thread.
        EMERGENCY_STOP is terminal -- cannot transition out of it.

        Args:
            mode: The :class:`InputMode` to transition to.

        Raises:
            InvalidStateError: If the gate is already in EMERGENCY_STOP and
                *mode* is anything other than EMERGENCY_STOP (terminal state).
        """
        with self._lock:
            old = self._mode
            if old is InputMode.EMERGENCY_STOP and mode is not InputMode.EMERGENCY_STOP:
                raise InvalidStateError(
                    "Cannot transition out of EMERGENCY_STOP"
                )
            if old is mode:
                return
            self._mode = mode
            # Snapshot the listener list while holding the lock so that
            # concurrent add/remove doesn't cause issues.
            listeners = list(self._listeners)

        # Fire listeners outside the lock to avoid deadlocks.
        for cb in listeners:
            try:
                cb(old, mode)
            except Exception:
                log.exception(
                    "Mode-change listener %r raised during %s -> %s",
                    cb, old.name, mode.name,
                )

    def check(self) -> None:
        """Called before every agent input operation.

        * **AGENT_SOLO** -- returns immediately (pass-through).
        * **COWORK** -- returns immediately (caller handles scheduling).
        * **HUMAN_OVERRIDE** -- raises :class:`AgentPreempted`.
        * **HUMAN_HOME** -- raises :class:`AgentPaused`.
        * **EMERGENCY_STOP** -- raises :class:`EmergencyStop`.
        """
        mode = self._mode  # single read; no lock needed for enum assignment
        if mode is InputMode.AGENT_SOLO or mode is InputMode.COWORK:
            return
        if mode is InputMode.HUMAN_OVERRIDE:
            raise AgentPreempted("Human has taken control")
        if mode is InputMode.HUMAN_HOME:
            raise AgentPaused("Agent is paused — user desktop active")
        if mode is InputMode.EMERGENCY_STOP:
            raise EmergencyStop("Session terminated by user")

    # ------------------------------------------------------------------
    # Listener management
    # ------------------------------------------------------------------

    def on_mode_change(
        self, callback: Callable[[InputMode, InputMode], None]
    ) -> None:
        """Register a listener for mode transitions.

        The *callback* receives ``(old_mode, new_mode)`` and is called
        synchronously in the thread that invokes :meth:`set_mode`.
        """
        with self._lock:
            self._listeners.append(callback)

    def remove_listener(self, callback: Callable) -> None:
        """Remove a previously registered listener.

        Silently does nothing if the callback is not in the list.
        """
        with self._lock:
            try:
                self._listeners.remove(callback)
            except ValueError:
                pass
