"""DesktopController — orchestrates mode transitions.

Wires :class:`HotkeyService`, :class:`InputGate`, and :class:`DesktopManager`
together so that hotkey presses trigger mode changes, desktop switches, and
emergency stops in a coordinated way.
"""

from __future__ import annotations

import logging
import threading
from types import TracebackType

from windowspc_mcp.confinement.errors import InvalidStateError
from windowspc_mcp.desktop.gate import InputGate, InputMode
from windowspc_mcp.desktop.hotkeys import HotkeyId, HotkeyService
from windowspc_mcp.desktop.manager import DesktopManager

log = logging.getLogger(__name__)

# Mode cycle for toggle_mode: AGENT_SOLO -> COWORK -> HUMAN_HOME -> AGENT_SOLO
_TOGGLE_CYCLE: dict[InputMode, InputMode] = {
    InputMode.AGENT_SOLO: InputMode.COWORK,
    InputMode.COWORK: InputMode.HUMAN_HOME,
    InputMode.HUMAN_HOME: InputMode.AGENT_SOLO,
}

# Modes where the agent desktop should be active
_AGENT_DESKTOP_MODES = frozenset({InputMode.AGENT_SOLO, InputMode.COWORK})


class DesktopController:
    """Orchestrate mode transitions between HotkeyService, InputGate, and DesktopManager.

    Thread-safe: all mode-transition methods are serialised through an internal
    lock so that concurrent hotkey presses cannot cause inconsistent state.
    """

    def __init__(
        self,
        desktop_manager: DesktopManager,
        input_gate: InputGate,
        hotkey_service: HotkeyService,
    ) -> None:
        """Wire components together.  Don't start anything yet."""
        self._dm = desktop_manager
        self._gate = input_gate
        self._hotkeys = hotkey_service
        self._lock = threading.Lock()
        self._pre_override_mode: InputMode | None = None
        self._started = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, initial_mode: InputMode = InputMode.AGENT_SOLO) -> None:
        """Start the controller.

        1. Create agent desktop (via desktop_manager).
        2. Wire hotkey callbacks to mode transition methods.
        3. Start hotkey service.
        4. Set initial mode on input_gate.
        5. If initial mode is AGENT_SOLO, switch to agent desktop.
        """
        with self._lock:
            if self._started:
                raise InvalidStateError("DesktopController is already started")

            self._dm.create_agent_desktop()

            self._hotkeys.start({
                HotkeyId.TOGGLE: self.toggle_mode,
                HotkeyId.OVERRIDE: self.override,
                HotkeyId.EMERGENCY: self.emergency_stop,
            })

            self._gate.set_mode(initial_mode)

            if initial_mode in _AGENT_DESKTOP_MODES:
                self._dm.switch_to_agent()

            self._started = True
            log.info("DesktopController started in %s mode", initial_mode.name)

    def stop(self) -> None:
        """Clean shutdown.

        1. Stop hotkey service.
        2. Switch to user desktop.
        3. Destroy agent desktop.
        """
        with self._lock:
            if not self._started:
                return
            self._hotkeys.stop()
            self._dm.switch_to_user()
            self._dm.destroy()
            self._started = False
            log.info("DesktopController stopped")

    def toggle_mode(self) -> None:
        """Cycle: AGENT_SOLO -> COWORK -> HUMAN_HOME -> AGENT_SOLO.

        Called by Ctrl+Alt+Space hotkey.
        Each transition updates InputGate and switches desktop as needed.
        """
        with self._lock:
            current = self._gate.mode

            if current in (InputMode.HUMAN_OVERRIDE, InputMode.EMERGENCY_STOP):
                log.debug(
                    "toggle_mode ignored in %s — must use "
                    "resume_from_override or restart",
                    current.name,
                )
                return

            next_mode = _TOGGLE_CYCLE.get(current)
            if next_mode is None:
                log.warning("toggle_mode: unexpected mode %s", current.name)
                return

            self._gate.set_mode(next_mode)

            # Switch desktop based on the new mode.
            if next_mode in _AGENT_DESKTOP_MODES:
                self._dm.switch_to_agent()
            else:
                self._dm.switch_to_user()

            log.info("Toggled mode: %s -> %s", current.name, next_mode.name)

    def override(self) -> None:
        """Instant HUMAN_OVERRIDE from any mode.

        Called by Ctrl+Alt+Enter hotkey.
        Saves current mode, sets InputGate to HUMAN_OVERRIDE, and switches
        to user desktop if on agent desktop.
        """
        with self._lock:
            current = self._gate.mode

            if current is InputMode.EMERGENCY_STOP:
                log.debug("override ignored in EMERGENCY_STOP")
                return

            if current is InputMode.HUMAN_OVERRIDE:
                log.debug("override ignored — already in HUMAN_OVERRIDE")
                return

            self._pre_override_mode = current
            self._gate.set_mode(InputMode.HUMAN_OVERRIDE)

            # If we were on the agent desktop, switch to user.
            if current in _AGENT_DESKTOP_MODES:
                self._dm.switch_to_user()

            log.info(
                "Override activated: %s -> HUMAN_OVERRIDE (saved %s)",
                current.name, current.name,
            )

    def resume_from_override(self) -> None:
        """Exit HUMAN_OVERRIDE back to the previous mode.

        Only valid when current mode is HUMAN_OVERRIDE.
        Restores the mode that was active before override.
        """
        with self._lock:
            current = self._gate.mode
            if current is not InputMode.HUMAN_OVERRIDE:
                raise InvalidStateError(
                    f"resume_from_override requires HUMAN_OVERRIDE, "
                    f"but current mode is {current.name}"
                )

            restored = self._pre_override_mode
            if restored is None:
                raise InvalidStateError(
                    "No pre-override mode saved — cannot resume"
                )

            self._gate.set_mode(restored)
            self._pre_override_mode = None

            # Switch desktop if the restored mode needs the agent desktop.
            if restored in _AGENT_DESKTOP_MODES:
                self._dm.switch_to_agent()

            log.info("Resumed from override -> %s", restored.name)

    def emergency_stop(self) -> None:
        """EMERGENCY_STOP from any mode.

        Called by Ctrl+Alt+Break hotkey.

        1. Set InputGate to EMERGENCY_STOP (terminal).
        2. Switch to user desktop.
        3. Destroy agent desktop (kills processes).
        4. Stop hotkey service.
        """
        with self._lock:
            current = self._gate.mode
            if current is InputMode.EMERGENCY_STOP:
                log.debug("emergency_stop: already stopped")
                return

            log.critical(
                "EMERGENCY STOP activated from %s mode", current.name
            )

            self._gate.set_mode(InputMode.EMERGENCY_STOP)
            self._dm.switch_to_user()
            self._dm.destroy()
            self._hotkeys.stop()
            self._started = False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def mode(self) -> InputMode:
        """Delegate to input_gate.mode."""
        return self._gate.mode

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> DesktopController:
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.stop()
