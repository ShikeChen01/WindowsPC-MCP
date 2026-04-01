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
from windowspc_mcp.desktop.capture import DesktopCapture
from windowspc_mcp.desktop.gate import InputGate, InputMode
from windowspc_mcp.desktop.hotkeys import HotkeyId, HotkeyService
from windowspc_mcp.desktop.manager import DesktopManager
from windowspc_mcp.desktop.viewer import ViewerWindow

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
        *,
        viewer_width: int = 1920,
        viewer_height: int = 1080,
        viewer_fps: int = 30,
    ) -> None:
        """Wire components together.  Don't start anything yet.

        Args:
            viewer_width: Agent desktop capture width (should match VDD resolution).
            viewer_height: Agent desktop capture height (should match VDD resolution).
            viewer_fps: Capture and display framerate.
        """
        self._dm = desktop_manager
        self._gate = input_gate
        self._hotkeys = hotkey_service
        self._lock = threading.Lock()
        self._pre_override_mode: InputMode | None = None
        self._started = False
        self._viewer_width = viewer_width
        self._viewer_height = viewer_height
        self._viewer_fps = viewer_fps
        self._capture: DesktopCapture | None = None
        self._viewer: ViewerWindow | None = None

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

            # Start desktop capture + viewer so user can watch agent desktop
            self._start_viewer()

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

        1. Stop viewer.
        2. Stop hotkey service.
        3. Switch to user desktop.
        4. Destroy agent desktop.

        Each step is exception-safe so that a failure in one does not
        prevent the remaining steps from executing.
        """
        with self._lock:
            if not self._started:
                return
            errors: list[str] = []
            for action, name in [
                (self._stop_viewer, "stop_viewer"),
                (self._hotkeys.stop, "hotkeys.stop"),
                (self._dm.switch_to_user, "switch_to_user"),
                (self._dm.destroy, "destroy"),
            ]:
                try:
                    action()
                except Exception:
                    log.exception("Error during %s", name)
                    errors.append(name)
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

            # Switch desktop based on the restored mode.
            if restored in _AGENT_DESKTOP_MODES:
                self._dm.switch_to_agent()
            else:
                self._dm.switch_to_user()

            log.info("Resumed from override -> %s", restored.name)

    def emergency_stop(self) -> None:
        """EMERGENCY_STOP from any mode.

        Called by Ctrl+Alt+Break hotkey.

        1. Set InputGate to EMERGENCY_STOP (terminal).
        2. Stop viewer.
        3. Switch to user desktop.
        4. Destroy agent desktop (kills processes).
        5. Stop hotkey service.

        Each teardown step is exception-safe so that a failure in one
        does not prevent the remaining steps from executing.
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
            for action, name in [
                (self._stop_viewer, "stop_viewer"),
                (self._dm.switch_to_user, "switch_to_user"),
                (self._dm.destroy, "destroy"),
                (self._hotkeys.stop, "hotkeys.stop"),
            ]:
                try:
                    action()
                except Exception:
                    log.exception("Error during emergency %s", name)
            self._started = False

    # ------------------------------------------------------------------
    # Viewer helpers (called with lock held)
    # ------------------------------------------------------------------

    def _start_viewer(self) -> None:
        """Start desktop capture and viewer window.  Must be called with lock held."""
        desktop_handle = self._dm.agent_desktop_handle
        if desktop_handle is None:
            log.warning("Cannot start viewer: no agent desktop handle")
            return

        self._capture = DesktopCapture(
            desktop_handle=desktop_handle,
            width=self._viewer_width,
            height=self._viewer_height,
            fps=self._viewer_fps,
        )
        self._capture.start()

        self._viewer = ViewerWindow(
            frame_buffer=self._capture.frame_buffer,
            fps=self._viewer_fps,
        )
        self._viewer.start()
        log.info(
            "Viewer started: %dx%d @ %d fps",
            self._viewer_width, self._viewer_height, self._viewer_fps,
        )

    def _stop_viewer(self) -> None:
        """Stop viewer and capture.  Must be called with lock held.  Idempotent."""
        if self._viewer is not None:
            self._viewer.stop()
            self._viewer = None
        if self._capture is not None:
            self._capture.stop()
            self._capture = None
        log.debug("Viewer stopped")

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
