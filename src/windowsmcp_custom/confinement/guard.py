"""Tool execution guard — checks server state before allowing tool execution."""

import logging
from windowsmcp_custom.server import ServerStateManager, ServerState
from windowsmcp_custom.confinement.engine import ConfinementEngine, ActionType
from windowsmcp_custom.confinement.errors import InvalidStateError, DisplayUnavailableError

logger = logging.getLogger(__name__)


class ToolGuard:
    def __init__(self, state_manager: ServerStateManager, confinement: ConfinementEngine):
        self._state = state_manager
        self._confinement = confinement

    def check(self, tool_name: str) -> str | None:
        """Check if a tool is allowed. Returns error message string or None.

        Note: returns strings (not exceptions) because the @guarded_tool decorator
        handles the conversion. Direct callers get a string they can return from the tool.
        """
        action = self._confinement.classify_action(tool_name)
        state = self._state.state

        if state == ServerState.SHUTTING_DOWN:
            return "Server is shutting down. No tools available."
        if state == ServerState.INIT:
            if action != ActionType.UNCONFINED:
                return f"Cannot use {tool_name}: server initializing. Call CreateScreen first."
        if action == ActionType.WRITE:
            if not self._state.is_gui_write_available:
                if state == ServerState.DRIVER_MISSING:
                    return f"Cannot use {tool_name}: Parsec VDD driver not installed."
                elif state == ServerState.DEGRADED:
                    reason = self._state._degraded_reason or "unknown"
                    return f"Cannot use {tool_name}: server degraded ({reason})."
                else:
                    return f"Cannot use {tool_name}: agent screen not active. Call CreateScreen first."
        if action == ActionType.READ:
            if not self._state.is_gui_available:
                if state == ServerState.DRIVER_MISSING:
                    return f"Cannot use {tool_name}: Parsec VDD driver not installed."
                return f"Cannot use {tool_name}: GUI not available ({state.value})."
        return None
