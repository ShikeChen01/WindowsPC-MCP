"""Server state machine for managing lifecycle and availability states."""

import logging
import threading
from enum import Enum
from typing import Callable, Optional

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

    def transition(self, new_state: ServerState, reason: Optional[str] = None) -> None:
        """
        Transition to a new state.

        Args:
            new_state: The target ServerState
            reason: Optional reason for the transition (stored for DEGRADED state)
        """
        with self._lock:
            old_state = self._state
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
