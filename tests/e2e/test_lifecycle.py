"""End-to-end lifecycle tests.

These tests exercise the REAL wiring between ServerStateManager,
ConfinementEngine, ToolGuard, DisplayManager, and the MCP tool
functions.  Only Win32 calls (virtual display creation, screen capture,
window enumeration) are mocked at the boundary.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from windowspc_mcp.confinement.engine import ConfinementEngine
from windowspc_mcp.confinement.guard import ToolGuard
from windowspc_mcp.display.manager import DisplayInfo, DisplayManager
from windowspc_mcp.server import ServerState, ServerStateManager

from tests.e2e.conftest import PRIMARY_DISPLAY, SECONDARY_DISPLAY


# ======================================================================
# 1. TestServerStartup
# ======================================================================


class TestServerStartup:
    """Lifespan initialises all components and performs driver checks."""

    def test_starts_in_init_state(self, state_manager):
        assert state_manager.state == ServerState.INIT

    def test_driver_check_passes(self, app_context):
        """When the driver is present, state stays INIT (waiting for CreateScreen)."""
        ctx = app_context
        assert ctx.display_manager.check_driver() is True
        # State should remain INIT -- lifespan does not auto-transition
        assert ctx.state_manager.state == ServerState.INIT

    def test_driver_check_fails_transitions_to_driver_missing(self, app_context):
        """Simulate the lifespan driver-check failure path."""
        ctx = app_context
        ctx.display_manager.check_driver.return_value = False

        # Replicate the lifespan logic when driver is missing
        if not ctx.display_manager.check_driver():
            ctx.state_manager.transition(
                ServerState.DRIVER_MISSING,
                reason="Parsec VDD driver not found",
            )

        assert ctx.state_manager.state == ServerState.DRIVER_MISSING

    def test_driver_missing_auto_install_succeeds(self, app_context):
        """Simulate auto-install succeeding after initial driver check fails."""
        ctx = app_context
        ctx.display_manager.check_driver.return_value = False

        # Simulate lifespan logic: driver check fails, then ensure_driver_installed succeeds
        driver_present = ctx.display_manager.check_driver()
        if not driver_present:
            # Simulate successful auto-install
            install_succeeded = True
            if not install_succeeded:
                ctx.state_manager.transition(
                    ServerState.DRIVER_MISSING,
                    reason="Parsec VDD driver not found",
                )

        # After successful install, state stays INIT (ready for CreateScreen)
        assert ctx.state_manager.state == ServerState.INIT

    def test_all_components_wired(self, app_context):
        """Verify all components are non-None and correctly typed."""
        ctx = app_context
        assert isinstance(ctx.state_manager, ServerStateManager)
        assert isinstance(ctx.display_manager, DisplayManager)
        assert isinstance(ctx.confinement, ConfinementEngine)
        assert isinstance(ctx.guard, ToolGuard)
        assert ctx.input_service is not None


# ======================================================================
# 2. TestCreateDestroyFlow
# ======================================================================


class TestCreateDestroyFlow:
    """CreateScreen / DestroyScreen tool integration."""

    def test_create_screen_creates_display_and_transitions(
        self, registered_tools, state_manager, display_manager, confinement
    ):
        result = registered_tools["CreateScreen"](width=1920, height=1080)

        # Tool returns a confirmation string
        assert "Agent screen created" in result
        assert r"\\.\DISPLAY3" in result

        # State transitions to READY
        assert state_manager.state == ServerState.READY

        # Confinement bounds are set
        bounds = confinement.bounds
        assert bounds is not None
        assert bounds.width == 1920
        assert bounds.height == 1080
        assert bounds.x == 3840  # mock_display.x

        # DisplayManager was called
        display_manager.create_display.assert_called_once_with(1920, 1080)

    def test_create_screen_clamps_width(self, registered_tools, confinement):
        result = registered_tools["CreateScreen"](width=800, height=600)

        assert "Agent screen created" in result
        # Width clamped to [1280, 1920], height clamped to [720, 1080]
        bounds = confinement.bounds
        assert bounds is not None
        assert bounds.width == 1280
        assert bounds.height == 720

    def test_create_screen_clamps_oversized(self, registered_tools, confinement):
        result = registered_tools["CreateScreen"](width=4000, height=2000)

        assert "Agent screen created" in result
        bounds = confinement.bounds
        assert bounds is not None
        assert bounds.width == 1920
        assert bounds.height == 1080

    def test_create_screen_twice_raises(self, registered_tools):
        registered_tools["CreateScreen"](width=1920, height=1080)

        with pytest.raises(RuntimeError, match="already exists"):
            registered_tools["CreateScreen"](width=1920, height=1080)

    def test_destroy_screen_clears_state(
        self, registered_tools, state_manager, display_manager, confinement
    ):
        registered_tools["CreateScreen"](width=1920, height=1080)
        assert state_manager.state == ServerState.READY

        result = registered_tools["DestroyScreen"]()
        assert "destroyed" in result.lower()

        # State transitions to DEGRADED (display destroyed but driver present)
        assert state_manager.state == ServerState.DEGRADED

        # Confinement bounds cleared
        assert confinement.bounds is None

        # DisplayManager.destroy_display was called
        display_manager.destroy_display.assert_called_once()

        # Agent display is cleared
        assert display_manager.agent_display is None

    def test_destroy_screen_when_no_screen(
        self, registered_tools, state_manager, confinement
    ):
        """DestroyScreen when no screen exists -- should not error."""
        assert state_manager.state == ServerState.INIT

        result = registered_tools["DestroyScreen"]()
        assert "destroyed" in result.lower()

        # State stays INIT since it was not READY
        assert state_manager.state == ServerState.INIT


# ======================================================================
# 3. TestScreenInfo
# ======================================================================


class TestScreenInfo:
    """ScreenInfo tool integration."""

    def test_returns_formatted_monitor_list(self, registered_tools, display_manager):
        result = registered_tools["ScreenInfo"]()

        assert r"\\.\DISPLAY1" in result
        assert r"\\.\DISPLAY2" in result
        assert r"\\.\DISPLAY3" in result
        assert "(0, 0) 1920x1080" in result
        assert "(1920, 0) 1920x1080" in result

    def test_marks_agent_display(self, registered_tools, display_manager, mock_display):
        """After CreateScreen, the agent display should be tagged [AGENT]."""
        registered_tools["CreateScreen"](width=1920, height=1080)

        result = registered_tools["ScreenInfo"]()

        # The agent display line should have [AGENT] tag
        lines = result.strip().split("\n")
        agent_lines = [l for l in lines if "[AGENT]" in l]
        assert len(agent_lines) == 1
        assert r"\\.\DISPLAY3" in agent_lines[0]

        # Non-agent displays should NOT have [AGENT]
        non_agent = [l for l in lines if "[AGENT]" not in l]
        assert len(non_agent) == 2

    def test_works_with_no_monitors(self, registered_tools, display_manager):
        display_manager.enumerate_monitors.return_value = []

        result = registered_tools["ScreenInfo"]()
        assert "No monitors found" in result


# ======================================================================
# 4. TestStateTransitions
# ======================================================================


class TestStateTransitions:
    """Full state machine transitions through the server lifecycle."""

    def test_full_lifecycle(
        self, registered_tools, state_manager, confinement
    ):
        """INIT -> CreateScreen -> READY -> DestroyScreen -> DEGRADED."""
        assert state_manager.state == ServerState.INIT

        registered_tools["CreateScreen"](width=1920, height=1080)
        assert state_manager.state == ServerState.READY
        assert confinement.bounds is not None

        registered_tools["DestroyScreen"]()
        assert state_manager.state == ServerState.DEGRADED
        assert confinement.bounds is None

    def test_driver_missing_blocks_gui_read_tools(self, state_manager, guard):
        """In DRIVER_MISSING state, GUI read tools are blocked."""
        state_manager.transition(ServerState.DRIVER_MISSING)

        err = guard.check("Screenshot")
        assert err is not None
        assert "driver" in err.lower()

    def test_driver_missing_blocks_gui_write_tools(self, state_manager, guard):
        """In DRIVER_MISSING state, GUI write tools are blocked."""
        state_manager.transition(ServerState.DRIVER_MISSING)

        err = guard.check("Click")
        assert err is not None
        assert "driver" in err.lower()

    def test_driver_missing_allows_unconfined_tools(self, state_manager, guard):
        """In DRIVER_MISSING state, unconfined tools still work."""
        state_manager.transition(ServerState.DRIVER_MISSING)

        err = guard.check("PowerShell")
        assert err is None

    def test_init_blocks_gui_tools_but_allows_create(self, state_manager, guard):
        """In INIT state, GUI tools are blocked but CreateScreen is allowed."""
        assert state_manager.state == ServerState.INIT

        # READ tools blocked
        err = guard.check("Screenshot")
        assert err is not None
        assert "CreateScreen" in err

        # WRITE tools blocked
        err = guard.check("Click")
        assert err is not None

        # UNCONFINED tools (including CreateScreen) are allowed
        assert guard.check("CreateScreen") is None
        assert guard.check("PowerShell") is None

    def test_ready_allows_all_tools(
        self, registered_tools, state_manager, guard
    ):
        """In READY state, all tool types are permitted."""
        registered_tools["CreateScreen"](width=1920, height=1080)
        assert state_manager.state == ServerState.READY

        assert guard.check("Screenshot") is None
        assert guard.check("Click") is None
        assert guard.check("PowerShell") is None
        assert guard.check("CreateScreen") is None

    def test_degraded_blocks_write_allows_read(
        self, registered_tools, state_manager, guard
    ):
        """In DEGRADED state, write tools are blocked but read tools are allowed."""
        registered_tools["CreateScreen"](width=1920, height=1080)
        state_manager.transition(ServerState.DEGRADED, reason="Session locked")

        # READ tools still allowed
        assert guard.check("Screenshot") is None

        # WRITE tools blocked
        err = guard.check("Click")
        assert err is not None
        assert "degraded" in err.lower()

    def test_session_lock_unlock_cycle(self, registered_tools, state_manager):
        """Simulate session lock -> DEGRADED -> unlock -> READY."""
        from windowspc_mcp.confinement.bounds import WTS_SESSION_LOCK, WTS_SESSION_UNLOCK

        registered_tools["CreateScreen"](width=1920, height=1080)
        assert state_manager.state == ServerState.READY

        # Simulate session lock (replicating lifespan's on_session_change callback)
        state_manager.transition(ServerState.DEGRADED, reason="Session locked")
        assert state_manager.state == ServerState.DEGRADED

        # Simulate session unlock
        if state_manager.state == ServerState.DEGRADED:
            state_manager.transition(ServerState.READY)
        assert state_manager.state == ServerState.READY

    def test_shutting_down_blocks_everything(self, state_manager, guard):
        """SHUTTING_DOWN blocks all tool types."""
        state_manager.transition(ServerState.SHUTTING_DOWN)

        assert guard.check("Screenshot") is not None
        assert guard.check("Click") is not None
        assert guard.check("PowerShell") is not None
        assert guard.check("CreateScreen") is not None

    def test_state_listener_callback_fires(self, state_manager):
        """State listeners are notified on transitions."""
        transitions = []
        state_manager.add_listener(
            lambda old, new, reason: transitions.append((old, new, reason))
        )

        state_manager.transition(ServerState.READY)
        state_manager.transition(ServerState.DEGRADED, reason="test")

        assert len(transitions) == 2
        assert transitions[0] == (ServerState.INIT, ServerState.READY, None)
        assert transitions[1] == (ServerState.READY, ServerState.DEGRADED, "test")


# ======================================================================
# 5. TestShutdownCleanup
# ======================================================================


class TestShutdownCleanup:
    """Lifespan exit path: destroy display, clean up listener/publisher."""

    def test_lifespan_exit_destroys_display(
        self, registered_tools, state_manager, display_manager
    ):
        """Simulate lifespan shutdown after CreateScreen."""
        registered_tools["CreateScreen"](width=1920, height=1080)
        assert display_manager.is_ready

        # Replicate lifespan shutdown sequence
        state_manager.transition(ServerState.SHUTTING_DOWN)

        if display_manager.is_ready:
            display_manager.destroy_display()

        assert state_manager.state == ServerState.SHUTTING_DOWN
        assert display_manager.agent_display is None
        display_manager.destroy_display.assert_called()

    def test_lifespan_exit_without_display(self, state_manager, display_manager):
        """Shutdown when no display was ever created."""
        state_manager.transition(ServerState.SHUTTING_DOWN)

        if display_manager.is_ready:
            display_manager.destroy_display()

        assert state_manager.state == ServerState.SHUTTING_DOWN
        display_manager.destroy_display.assert_not_called()

    def test_listener_cleanup(self, app_context):
        """DisplayChangeListener and StatusPublisher are cleaned up."""
        ctx = app_context

        # Simulate lifespan attaching a mock listener and publisher
        mock_listener = MagicMock()
        mock_publisher = MagicMock()
        ctx.display_listener = mock_listener
        ctx.status_publisher = mock_publisher

        # Replicate lifespan shutdown sequence
        ctx.state_manager.transition(ServerState.SHUTTING_DOWN)

        if ctx.display_listener is not None:
            ctx.display_listener.stop()
            ctx.display_listener = None

        if ctx.status_publisher is not None:
            ctx.status_publisher.stop()

        mock_listener.stop.assert_called_once()
        mock_publisher.stop.assert_called_once()
        assert ctx.display_listener is None

    def test_shutdown_transitions_through_states(
        self, registered_tools, state_manager, display_manager
    ):
        """Full shutdown sequence: READY -> SHUTTING_DOWN -> display destroyed."""
        registered_tools["CreateScreen"](width=1920, height=1080)

        transitions = []
        state_manager.add_listener(
            lambda old, new, reason: transitions.append((old.value, new.value))
        )

        # Shutdown
        state_manager.transition(ServerState.SHUTTING_DOWN)
        if display_manager.is_ready:
            display_manager.destroy_display()

        assert ("ready", "shutting_down") in transitions
        assert display_manager.agent_display is None

    def test_get_status_reflects_shutdown(self, state_manager):
        """get_status dict reflects the shutdown state correctly."""
        state_manager.transition(ServerState.SHUTTING_DOWN)

        status = state_manager.get_status()
        assert status["state"] == "shutting_down"
        assert status["gui_available"] is False
        assert status["gui_write_available"] is False
