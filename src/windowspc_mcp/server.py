"""Server state machine for managing lifecycle and availability states."""

import logging
import threading
from enum import Enum
from typing import Callable, Optional

from windowspc_mcp.confinement.errors import InvalidStateError

logger = logging.getLogger(__name__)


class ServerState(Enum):
    """Enumeration of possible server states."""

    INIT = "init"
    DRIVER_MISSING = "driver_missing"
    CREATING_DISPLAY = "creating_display"
    CREATE_FAILED = "create_failed"
    READY = "ready"
    DEGRADED = "degraded"
    RECOVERING = "recovering"
    SHUTTING_DOWN = "shutting_down"


class ServerStateManager:
    """Manages server state transitions and availability."""

    _VALID_TRANSITIONS: dict[ServerState, set[ServerState]] = {
        ServerState.INIT: {
            ServerState.READY,
            ServerState.DRIVER_MISSING,
            ServerState.CREATING_DISPLAY,
            ServerState.SHUTTING_DOWN,
        },
        ServerState.DRIVER_MISSING: {ServerState.INIT, ServerState.SHUTTING_DOWN},
        ServerState.CREATING_DISPLAY: {
            ServerState.READY,
            ServerState.CREATE_FAILED,
            ServerState.SHUTTING_DOWN,
        },
        ServerState.CREATE_FAILED: {
            ServerState.CREATING_DISPLAY,
            ServerState.SHUTTING_DOWN,
        },
        ServerState.READY: {
            ServerState.DEGRADED,
            ServerState.RECOVERING,
            ServerState.SHUTTING_DOWN,
        },
        ServerState.DEGRADED: {
            ServerState.READY,
            ServerState.RECOVERING,
            ServerState.SHUTTING_DOWN,
        },
        ServerState.RECOVERING: {
            ServerState.READY,
            ServerState.DEGRADED,
            ServerState.SHUTTING_DOWN,
        },
        ServerState.SHUTTING_DOWN: set(),
    }

    def __init__(self) -> None:
        """Initialize the state manager with INIT state."""
        self._lock = threading.RLock()
        self._state = ServerState.INIT
        self._state_listeners: list[Callable[[ServerState, ServerState, Optional[str]], None]] = []
        self._degraded_reason: Optional[str] = None

    @property
    def state(self) -> ServerState:
        """Get the current server state."""
        return self._state

    @property
    def is_gui_available(self) -> bool:
        """Check if GUI is available (READY or DEGRADED states)."""
        return self._state in (ServerState.READY, ServerState.DEGRADED)

    @property
    def is_gui_write_available(self) -> bool:
        """Check if GUI write operations are available (READY state only)."""
        return self._state == ServerState.READY

    @property
    def is_unconfined_available(self) -> bool:
        """Check if unconfined operations are available (not INIT or SHUTTING_DOWN)."""
        return self._state not in (ServerState.INIT, ServerState.SHUTTING_DOWN)

    @property
    def degraded_reason(self) -> str:
        """The reason for DEGRADED state, or None if not degraded."""
        with self._lock:
            return self._degraded_reason

    def transition(self, new_state: ServerState, reason: Optional[str] = None) -> None:
        """
        Transition to a new state.

        Args:
            new_state: The target ServerState
            reason: Optional reason for the transition (stored for DEGRADED state)

        Raises:
            InvalidStateError: If the transition is not allowed by the state machine.
        """
        with self._lock:
            old_state = self._state
            allowed = self._VALID_TRANSITIONS.get(old_state, set())
            if new_state is not old_state and new_state not in allowed:
                raise InvalidStateError(
                    f"Invalid state transition: {old_state.value} -> {new_state.value}"
                )
            self._state = new_state

            if new_state == ServerState.DEGRADED:
                self._degraded_reason = reason
            else:
                self._degraded_reason = None

            logger.info(
                f"State transition: {old_state.value} -> {new_state.value}"
                + (f" (reason: {reason})" if reason else "")
            )

            # Snapshot listeners before iterating to avoid holding the lock during callbacks
            listeners = list(self._state_listeners)

        # Call listeners outside the lock to avoid deadlocks
        for listener in listeners:
            listener(old_state, new_state, reason)

    def add_listener(
        self, callback: Callable[[ServerState, ServerState, Optional[str]], None]
    ) -> None:
        """
        Register a listener to be called on state transitions.

        Args:
            callback: Function with signature (old_state, new_state, reason)
        """
        with self._lock:
            self._state_listeners.append(callback)

    def get_status(self) -> dict:
        """
        Get the current server status.

        Returns:
            Dictionary with state, gui_available, gui_write_available, and degraded_reason
        """
        with self._lock:
            return {
                "state": self._state.value,
                "gui_available": self.is_gui_available,
                "gui_write_available": self.is_gui_write_available,
                "degraded_reason": self._degraded_reason,
            }
