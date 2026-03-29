"""Smoke: real server component initialization — no mocks.

Tests that the real objects can be constructed and wired together.
"""

from windowspc_mcp.server import ServerStateManager, ServerState
from windowspc_mcp.confinement.engine import ConfinementEngine
from windowspc_mcp.confinement.guard import ToolGuard
from windowspc_mcp.input.service import AgentInputService
from windowspc_mcp.display.manager import DisplayManager


class TestRealComponentConstruction:
    """Every component must instantiate without crashing."""

    def test_state_manager(self):
        sm = ServerStateManager()
        assert sm.state == ServerState.INIT

    def test_display_manager(self):
        dm = DisplayManager()
        assert dm.agent_display is None
        assert not dm.is_ready

    def test_confinement_engine(self):
        ce = ConfinementEngine()
        assert ce.bounds is None

    def test_tool_guard(self):
        sm = ServerStateManager()
        ce = ConfinementEngine()
        guard = ToolGuard(sm, ce)
        # In INIT state, UNCONFINED tools should pass
        assert guard.check("CreateScreen") is None
        # GUI tools should be blocked
        assert guard.check("Click") is not None

    def test_input_service(self):
        ce = ConfinementEngine()
        svc = AgentInputService(agent_bounds_fn=lambda: ce.bounds)
        assert svc is not None


class TestRealComponentWiring:
    """Components wired together behave correctly."""

    def test_guard_reflects_state_transitions(self):
        sm = ServerStateManager()
        ce = ConfinementEngine()
        guard = ToolGuard(sm, ce)

        # INIT: Click blocked
        assert guard.check("Click") is not None

        # Simulate CreateScreen
        sm.transition(ServerState.READY)
        assert guard.check("Click") is None

        # Simulate DestroyScreen
        sm.transition(ServerState.DEGRADED, reason="destroyed")
        assert guard.check("Click") is not None  # write blocked
        assert guard.check("Screenshot") is None  # read allowed

        # Shutdown
        sm.transition(ServerState.SHUTTING_DOWN)
        assert guard.check("Click") is not None
        assert guard.check("Screenshot") is not None
        assert guard.check("PowerShell") is not None

    def test_confinement_translate_roundtrip(self):
        from tests.conftest import MockBounds
        ce = ConfinementEngine()
        ce.set_agent_bounds(MockBounds(x=3840, y=0, width=1920, height=1080))

        abs_x, abs_y = ce.validate_and_translate(100, 200)
        assert abs_x == 3940
        assert abs_y == 200
        assert ce.is_point_on_agent_screen(abs_x, abs_y)

    def test_monitor_enumeration_does_not_crash(self):
        dm = DisplayManager()
        monitors = dm.enumerate_monitors()
        assert isinstance(monitors, list)
        # Should find at least one monitor on any Windows machine
        assert len(monitors) >= 1
        for m in monitors:
            assert m.width > 0
            assert m.height > 0
