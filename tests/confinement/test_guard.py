"""Tests for windowspc_mcp.confinement.guard — ToolGuard.check() all branches."""

import pytest

from windowspc_mcp.confinement.engine import ConfinementEngine
from windowspc_mcp.confinement.errors import ConfinementError
from windowspc_mcp.confinement.guard import ToolGuard
from windowspc_mcp.server import ServerStateManager, ServerState
from tests.conftest import MockBounds


@pytest.fixture
def state_manager():
    return ServerStateManager()


@pytest.fixture
def confinement():
    engine = ConfinementEngine()
    engine.set_agent_bounds(MockBounds())
    return engine


@pytest.fixture
def guard(state_manager, confinement):
    return ToolGuard(state_manager, confinement)


# ---------------------------------------------------------------------------
# SHUTTING_DOWN blocks everything
# ---------------------------------------------------------------------------


class TestShuttingDownBlocksAll:
    def test_blocks_write_tool(self, state_manager, guard):
        state_manager.transition(ServerState.SHUTTING_DOWN)
        result = guard.check("Click")
        assert result is not None
        assert "shutting down" in result.lower()

    def test_blocks_read_tool(self, state_manager, guard):
        state_manager.transition(ServerState.SHUTTING_DOWN)
        result = guard.check("Screenshot")
        assert result is not None
        assert "shutting down" in result.lower()

    def test_blocks_unconfined_tool(self, state_manager, guard):
        state_manager.transition(ServerState.SHUTTING_DOWN)
        result = guard.check("PowerShell")
        assert result is not None
        assert "shutting down" in result.lower()

    def test_unknown_tool_raises_confinement_error(self, state_manager, guard):
        state_manager.transition(ServerState.SHUTTING_DOWN)
        with pytest.raises(ConfinementError, match="Unknown tool"):
            guard.check("SomeFutureTool")


# ---------------------------------------------------------------------------
# INIT blocks non-UNCONFINED, allows UNCONFINED
# ---------------------------------------------------------------------------


class TestInitState:
    """ServerStateManager starts in INIT by default."""

    def test_blocks_write(self, guard):
        result = guard.check("Click")
        assert result is not None
        assert "initializing" in result.lower()

    def test_blocks_read(self, guard):
        result = guard.check("Screenshot")
        assert result is not None
        assert "initializing" in result.lower()

    def test_allows_unconfined(self, guard):
        result = guard.check("PowerShell")
        assert result is None

    def test_allows_create_screen(self, guard):
        result = guard.check("CreateScreen")
        assert result is None

    def test_allows_wait(self, guard):
        result = guard.check("Wait")
        assert result is None

    def test_error_includes_tool_name(self, guard):
        result = guard.check("Move")
        assert "Move" in result

    def test_error_suggests_create_screen(self, guard):
        result = guard.check("Type")
        assert "CreateScreen" in result


# ---------------------------------------------------------------------------
# WRITE actions in various states
# ---------------------------------------------------------------------------


class TestWriteInDriverMissing:
    def test_click_blocked(self, state_manager, guard):
        state_manager.transition(ServerState.DRIVER_MISSING)
        result = guard.check("Click")
        assert result is not None
        assert "driver" in result.lower()
        assert "Click" in result


class TestWriteInDegraded:
    def test_click_blocked_with_reason(self, state_manager, guard):
        state_manager.transition(ServerState.READY)
        state_manager.transition(ServerState.DEGRADED, reason="display lost")
        result = guard.check("Click")
        assert result is not None
        assert "degraded" in result.lower()
        assert "display lost" in result
        assert "Click" in result

    def test_degraded_without_explicit_reason(self, state_manager, guard):
        state_manager.transition(ServerState.READY)
        state_manager.transition(ServerState.DEGRADED)
        result = guard.check("Type")
        assert result is not None
        assert "degraded" in result.lower()
        assert "unknown" in result.lower()


class TestWriteInCreateFailed:
    def test_click_blocked(self, state_manager, guard):
        state_manager.transition(ServerState.CREATING_DISPLAY)
        state_manager.transition(ServerState.CREATE_FAILED)
        result = guard.check("Click")
        assert result is not None
        assert "not active" in result.lower()
        assert "Click" in result

    def test_scroll_blocked(self, state_manager, guard):
        state_manager.transition(ServerState.CREATING_DISPLAY)
        state_manager.transition(ServerState.CREATE_FAILED)
        result = guard.check("Scroll")
        assert result is not None
        assert "Scroll" in result


class TestWriteInReady:
    def test_click_allowed(self, state_manager, guard):
        state_manager.transition(ServerState.READY)
        assert guard.check("Click") is None

    def test_type_allowed(self, state_manager, guard):
        state_manager.transition(ServerState.READY)
        assert guard.check("Type") is None

    def test_shortcut_allowed(self, state_manager, guard):
        state_manager.transition(ServerState.READY)
        assert guard.check("Shortcut") is None

    def test_all_write_tools_allowed(self, state_manager, guard):
        state_manager.transition(ServerState.READY)
        write_tools = [
            "Click", "Type", "Move", "Scroll", "Shortcut",
            "App", "MultiSelect", "MultiEdit", "RecoverWindow",
        ]
        for tool in write_tools:
            assert guard.check(tool) is None, f"{tool} should be allowed in READY"


# ---------------------------------------------------------------------------
# READ actions in various states
# ---------------------------------------------------------------------------


class TestReadInDriverMissing:
    def test_screenshot_blocked(self, state_manager, guard):
        state_manager.transition(ServerState.DRIVER_MISSING)
        result = guard.check("Screenshot")
        assert result is not None
        assert "driver" in result.lower()
        assert "Screenshot" in result


class TestReadInNonAvailableState:
    def test_create_failed_blocks_read(self, state_manager, guard):
        state_manager.transition(ServerState.CREATING_DISPLAY)
        state_manager.transition(ServerState.CREATE_FAILED)
        result = guard.check("Screenshot")
        assert result is not None
        assert "gui not available" in result.lower()

    def test_creating_display_blocks_read(self, state_manager, guard):
        state_manager.transition(ServerState.CREATING_DISPLAY)
        result = guard.check("Snapshot")
        assert result is not None
        assert "gui not available" in result.lower()

    def test_error_includes_state_value(self, state_manager, guard):
        state_manager.transition(ServerState.CREATING_DISPLAY)
        state_manager.transition(ServerState.CREATE_FAILED)
        result = guard.check("Scrape")
        assert "create_failed" in result.lower()


class TestReadInReady:
    def test_screenshot_allowed(self, state_manager, guard):
        state_manager.transition(ServerState.READY)
        assert guard.check("Screenshot") is None

    def test_snapshot_allowed(self, state_manager, guard):
        state_manager.transition(ServerState.READY)
        assert guard.check("Snapshot") is None


class TestReadInDegraded:
    def test_screenshot_allowed(self, state_manager, guard):
        state_manager.transition(ServerState.READY)
        state_manager.transition(ServerState.DEGRADED, reason="minor")
        assert guard.check("Screenshot") is None

    def test_scrape_allowed(self, state_manager, guard):
        state_manager.transition(ServerState.READY)
        state_manager.transition(ServerState.DEGRADED, reason="minor")
        assert guard.check("Scrape") is None


# ---------------------------------------------------------------------------
# Tool name appears in error messages
# ---------------------------------------------------------------------------


class TestToolNameInErrorMessages:
    @pytest.mark.parametrize(
        "tool",
        ["Click", "Screenshot"],
    )
    def test_tool_name_in_init_error(self, state_manager, guard, tool):
        # state_manager starts in INIT
        result = guard.check(tool)
        assert result is not None
        assert tool in result, f"Expected '{tool}' in error message: {result}"

    @pytest.mark.parametrize(
        "tool",
        ["Type", "Snapshot"],
    )
    def test_tool_name_in_driver_missing_error(self, state_manager, guard, tool):
        state_manager.transition(ServerState.DRIVER_MISSING)
        result = guard.check(tool)
        assert result is not None
        assert tool in result, f"Expected '{tool}' in error message: {result}"

    @pytest.mark.parametrize(
        "tool",
        ["Scroll", "Scrape"],
    )
    def test_tool_name_in_create_failed_error(self, state_manager, guard, tool):
        state_manager.transition(ServerState.CREATING_DISPLAY)
        state_manager.transition(ServerState.CREATE_FAILED)
        result = guard.check(tool)
        assert result is not None
        assert tool in result, f"Expected '{tool}' in error message: {result}"
