"""E2E tests for input tools exercising the full stack.

Build real ServerStateManager, ConfinementEngine, ToolGuard, AgentInputService.
Register tools on a real FastMCP. Mock only Win32 APIs and DisplayManager.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from dataclasses import dataclass, field

from mcp.server.fastmcp import FastMCP

from windowspc_mcp.server import ServerStateManager, ServerState
from windowspc_mcp.confinement.engine import ConfinementEngine, ScreenBounds
from windowspc_mcp.confinement.guard import ToolGuard
from windowspc_mcp.display.manager import DisplayInfo
from windowspc_mcp.tree.views import TreeState, TreeElementNode, ScrollElementNode, BoundingBox
from windowspc_mcp.tools import input as input_tools


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

AGENT_X, AGENT_Y = 3840, 0
AGENT_W, AGENT_H = 1920, 1080


def _make_display_info(
    x: int = AGENT_X,
    y: int = AGENT_Y,
    w: int = AGENT_W,
    h: int = AGENT_H,
    name: str = r"\\.\DISPLAY3",
) -> DisplayInfo:
    return DisplayInfo(device_name=name, x=x, y=y, width=w, height=h, is_agent=True)


def _make_tree_node(
    name: str, cx: int, cy: int, w: int = 100, h: int = 40
) -> TreeElementNode:
    """Create a TreeElementNode whose center is (cx, cy)."""
    half_w, half_h = w // 2, h // 2
    return TreeElementNode(
        name=name,
        control_type="Button",
        bounding_box=BoundingBox(
            left=cx - half_w,
            top=cy - half_h,
            right=cx + half_w,
            bottom=cy + half_h,
        ),
        window_name="TestApp",
    )


def _make_scroll_node(
    name: str, cx: int, cy: int, w: int = 200, h: int = 400
) -> ScrollElementNode:
    half_w, half_h = w // 2, h // 2
    return ScrollElementNode(
        name=name,
        control_type="ScrollBar",
        bounding_box=BoundingBox(
            left=cx - half_w,
            top=cy - half_h,
            right=cx + half_w,
            bottom=cy + half_h,
        ),
        window_name="TestApp",
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def state_manager():
    return ServerStateManager()


@pytest.fixture
def confinement():
    return ConfinementEngine()


@pytest.fixture
def guard(state_manager, confinement):
    return ToolGuard(state_manager, confinement)


@pytest.fixture
def display_manager():
    """Mock DisplayManager with an agent_display already configured."""
    dm = MagicMock()
    agent = _make_display_info()
    dm.agent_display = agent
    dm._latest_tree_state = None  # default: no tree state
    return dm


@pytest.fixture
def input_service():
    """Mock AgentInputService — all methods return deterministic strings."""
    svc = MagicMock()
    svc.click.side_effect = lambda ax, ay, btn, clicks: f"Clicked ({ax}, {ay}) [{btn} x{clicks}]"
    svc.type_text.side_effect = (
        lambda text, ax, ay, **kw: f"Typed {len(text)} chars"
    )
    svc.move.side_effect = lambda ax, ay, drag=False: f"{'Dragged' if drag else 'Moved'} to ({ax}, {ay})"
    svc.scroll.side_effect = (
        lambda ax, ay, amount, horiz: f"Scrolled {'horizontally' if horiz else 'vertically'} by {amount} at ({ax}, {ay})"
    )
    svc.send_shortcut.side_effect = lambda keys: f"Sent shortcut: {keys}"
    return svc


@pytest.fixture
def ready_stack(state_manager, confinement, guard, display_manager, input_service):
    """Full stack in READY state with tools registered on a real FastMCP.

    Returns a dict with all components + a ``tool(name)`` helper to get a tool fn.
    """
    # Set confinement bounds
    confinement.set_agent_bounds(_make_display_info())

    # Transition to READY
    state_manager.transition(ServerState.READY)

    # Create real FastMCP and register tools
    mcp = FastMCP("test-input-e2e")
    input_tools.register(
        mcp,
        get_display_manager=lambda: display_manager,
        get_confinement=lambda: confinement,
        get_state_manager=lambda: state_manager,
        get_guard=lambda: guard,
        get_input_service=lambda: input_service,
    )

    def _tool(name: str):
        t = mcp._tool_manager._tools.get(name)
        assert t is not None, f"Tool {name!r} not found. Available: {list(mcp._tool_manager._tools.keys())}"
        return t.fn

    return {
        "mcp": mcp,
        "state_manager": state_manager,
        "confinement": confinement,
        "guard": guard,
        "display_manager": display_manager,
        "input_service": input_service,
        "tool": _tool,
    }


# ============================================================================
# TestClickE2E
# ============================================================================


class TestClickE2E:
    """Click tool end-to-end tests."""

    def test_click_with_xy_validates_and_calls_service(self, ready_stack):
        click = ready_stack["tool"]("Click")
        result = click(x=100, y=200)

        svc = ready_stack["input_service"]
        svc.click.assert_called_once_with(AGENT_X + 100, AGENT_Y + 200, "left", 1)
        assert "Clicked" in result

    def test_click_with_label_resolves_from_tree_state(self, ready_stack):
        dm = ready_stack["display_manager"]
        # Place a node at absolute (AGENT_X + 500, AGENT_Y + 300) so it's on-screen
        node = _make_tree_node("OK Button", AGENT_X + 500, AGENT_Y + 300)
        dm._latest_tree_state = TreeState(interactive_nodes=[node])

        click = ready_stack["tool"]("Click")
        result = click(label=0)

        svc = ready_stack["input_service"]
        svc.click.assert_called_once()
        call_args = svc.click.call_args
        abs_x, abs_y = call_args[0][0], call_args[0][1]
        assert abs_x == AGENT_X + 500
        assert abs_y == AGENT_Y + 300
        assert "Clicked" in result

    def test_click_out_of_bounds_returns_confinement_error(self, ready_stack):
        click = ready_stack["tool"]("Click")
        result = click(x=5000, y=200)
        assert "Error" in result
        assert "out of bounds" in result

    def test_click_negative_coords_returns_confinement_error(self, ready_stack):
        click = ready_stack["tool"]("Click")
        result = click(x=-1, y=200)
        assert "Error" in result

    def test_click_not_ready_returns_guard_error(self, ready_stack):
        ready_stack["state_manager"].transition(
            ServerState.DEGRADED, reason="display lost"
        )
        click = ready_stack["tool"]("Click")
        result = click(x=100, y=200)
        assert "Cannot use Click" in result

    def test_right_click(self, ready_stack):
        click = ready_stack["tool"]("Click")
        result = click(x=100, y=200, button="right")

        svc = ready_stack["input_service"]
        svc.click.assert_called_once_with(AGENT_X + 100, AGENT_Y + 200, "right", 1)

    def test_double_click(self, ready_stack):
        click = ready_stack["tool"]("Click")
        result = click(x=100, y=200, clicks=2)

        svc = ready_stack["input_service"]
        svc.click.assert_called_once_with(AGENT_X + 100, AGENT_Y + 200, "left", 2)

    def test_click_missing_xy_and_label_returns_error(self, ready_stack):
        click = ready_stack["tool"]("Click")
        result = click()
        assert "Error" in result

    def test_click_label_no_tree_state_returns_error(self, ready_stack):
        # dm._latest_tree_state is None by default
        click = ready_stack["tool"]("Click")
        result = click(label=0)
        assert "Error" in result
        assert "tree state" in result.lower()

    def test_click_label_out_of_range_returns_error(self, ready_stack):
        dm = ready_stack["display_manager"]
        node = _make_tree_node("Only", AGENT_X + 100, AGENT_Y + 100)
        dm._latest_tree_state = TreeState(interactive_nodes=[node])

        click = ready_stack["tool"]("Click")
        result = click(label=99)
        assert "Error" in result
        assert "out of range" in result.lower()

    def test_click_middle_button(self, ready_stack):
        click = ready_stack["tool"]("Click")
        result = click(x=50, y=50, button="middle")

        svc = ready_stack["input_service"]
        svc.click.assert_called_once_with(AGENT_X + 50, AGENT_Y + 50, "middle", 1)


# ============================================================================
# TestTypeE2E
# ============================================================================


class TestTypeE2E:
    """Type tool end-to-end tests."""

    def test_type_with_xy_clicks_then_types(self, ready_stack):
        type_tool = ready_stack["tool"]("Type")
        result = type_tool(text="hello world", x=100, y=200)

        svc = ready_stack["input_service"]
        svc.type_text.assert_called_once_with(
            "hello world",
            AGENT_X + 100,
            AGENT_Y + 200,
            clear=False,
            caret_position="idle",
            press_enter=False,
        )
        assert "Typed" in result

    def test_type_with_label_resolves_coordinates(self, ready_stack):
        dm = ready_stack["display_manager"]
        node = _make_tree_node("Search Box", AGENT_X + 400, AGENT_Y + 50)
        dm._latest_tree_state = TreeState(interactive_nodes=[node])

        type_tool = ready_stack["tool"]("Type")
        result = type_tool(text="query", label=0)

        svc = ready_stack["input_service"]
        svc.type_text.assert_called_once()
        call_kw = svc.type_text.call_args
        abs_x = call_kw[0][1]
        abs_y = call_kw[0][2]
        assert abs_x == AGENT_X + 400
        assert abs_y == AGENT_Y + 50

    def test_type_with_clear_true(self, ready_stack):
        type_tool = ready_stack["tool"]("Type")
        type_tool(text="new text", x=10, y=10, clear=True)

        svc = ready_stack["input_service"]
        svc.type_text.assert_called_once()
        _, kwargs = svc.type_text.call_args
        assert kwargs["clear"] is True

    def test_type_with_caret_position_start(self, ready_stack):
        type_tool = ready_stack["tool"]("Type")
        type_tool(text="prefix", x=10, y=10, caret_position="start")

        svc = ready_stack["input_service"]
        _, kwargs = svc.type_text.call_args
        assert kwargs["caret_position"] == "start"

    def test_type_with_caret_position_end(self, ready_stack):
        type_tool = ready_stack["tool"]("Type")
        type_tool(text="suffix", x=10, y=10, caret_position="end")

        svc = ready_stack["input_service"]
        _, kwargs = svc.type_text.call_args
        assert kwargs["caret_position"] == "end"

    def test_type_with_press_enter(self, ready_stack):
        type_tool = ready_stack["tool"]("Type")
        type_tool(text="submit", x=10, y=10, press_enter=True)

        svc = ready_stack["input_service"]
        _, kwargs = svc.type_text.call_args
        assert kwargs["press_enter"] is True

    def test_type_string_to_bool_conversion_clear(self, ready_stack):
        type_tool = ready_stack["tool"]("Type")
        type_tool(text="abc", x=10, y=10, clear="true")

        svc = ready_stack["input_service"]
        _, kwargs = svc.type_text.call_args
        assert kwargs["clear"] is True

    def test_type_string_to_bool_conversion_false(self, ready_stack):
        type_tool = ready_stack["tool"]("Type")
        type_tool(text="abc", x=10, y=10, clear="false")

        svc = ready_stack["input_service"]
        _, kwargs = svc.type_text.call_args
        assert kwargs["clear"] is False

    def test_type_string_to_bool_press_enter(self, ready_stack):
        type_tool = ready_stack["tool"]("Type")
        type_tool(text="abc", x=10, y=10, press_enter="true")

        svc = ready_stack["input_service"]
        _, kwargs = svc.type_text.call_args
        assert kwargs["press_enter"] is True

    def test_type_without_coords_types_at_current_position(self, ready_stack):
        type_tool = ready_stack["tool"]("Type")
        type_tool(text="no click")

        svc = ready_stack["input_service"]
        svc.type_text.assert_called_once_with(
            "no click",
            None,
            None,
            clear=False,
            caret_position="idle",
            press_enter=False,
        )

    def test_type_label_no_tree_state_returns_error(self, ready_stack):
        type_tool = ready_stack["tool"]("Type")
        result = type_tool(text="x", label=0)
        assert "Error" in result
        assert "tree state" in result.lower()

    def test_type_label_out_of_range_returns_error(self, ready_stack):
        dm = ready_stack["display_manager"]
        node = _make_tree_node("Only", AGENT_X + 100, AGENT_Y + 100)
        dm._latest_tree_state = TreeState(interactive_nodes=[node])

        type_tool = ready_stack["tool"]("Type")
        result = type_tool(text="x", label=99)
        assert "Error" in result
        assert "out of range" in result.lower()


# ============================================================================
# TestMoveE2E
# ============================================================================


class TestMoveE2E:
    """Move tool end-to-end tests."""

    def test_move_validates_coords_through_confinement(self, ready_stack):
        move = ready_stack["tool"]("Move")
        result = move(x=500, y=400)

        svc = ready_stack["input_service"]
        svc.move.assert_called_once_with(AGENT_X + 500, AGENT_Y + 400, drag=False)
        assert "Moved" in result

    def test_move_with_drag(self, ready_stack):
        move = ready_stack["tool"]("Move")
        result = move(x=100, y=100, drag=True)

        svc = ready_stack["input_service"]
        svc.move.assert_called_once_with(AGENT_X + 100, AGENT_Y + 100, drag=True)
        assert "Dragged" in result

    def test_move_out_of_bounds_returns_error(self, ready_stack):
        move = ready_stack["tool"]("Move")
        result = move(x=9999, y=9999)
        assert "Error" in result
        assert "out of bounds" in result

    def test_move_negative_coords_returns_error(self, ready_stack):
        move = ready_stack["tool"]("Move")
        result = move(x=-10, y=50)
        assert "Error" in result

    def test_move_drag_string_to_bool(self, ready_stack):
        move = ready_stack["tool"]("Move")
        result = move(x=100, y=100, drag="true")

        svc = ready_stack["input_service"]
        svc.move.assert_called_once_with(AGENT_X + 100, AGENT_Y + 100, drag=True)

    def test_move_at_boundary(self, ready_stack):
        """Move to the last valid pixel (width-1, height-1)."""
        move = ready_stack["tool"]("Move")
        result = move(x=AGENT_W - 1, y=AGENT_H - 1)

        svc = ready_stack["input_service"]
        svc.move.assert_called_once_with(
            AGENT_X + AGENT_W - 1,
            AGENT_Y + AGENT_H - 1,
            drag=False,
        )

    def test_move_at_exact_boundary_returns_error(self, ready_stack):
        """Move to x=width or y=height should fail (exclusive upper bound)."""
        move = ready_stack["tool"]("Move")
        result = move(x=AGENT_W, y=0)
        assert "Error" in result


# ============================================================================
# TestScrollE2E
# ============================================================================


class TestScrollE2E:
    """Scroll tool end-to-end tests."""

    def test_scroll_validates_coords(self, ready_stack):
        scroll = ready_stack["tool"]("Scroll")
        result = scroll(x=500, y=400)

        svc = ready_stack["input_service"]
        svc.scroll.assert_called_once_with(AGENT_X + 500, AGENT_Y + 400, -3, False)
        assert "Scrolled" in result

    def test_scroll_negative_amount(self, ready_stack):
        scroll = ready_stack["tool"]("Scroll")
        result = scroll(x=100, y=100, amount=-5)

        svc = ready_stack["input_service"]
        svc.scroll.assert_called_once_with(AGENT_X + 100, AGENT_Y + 100, -5, False)

    def test_scroll_positive_amount(self, ready_stack):
        scroll = ready_stack["tool"]("Scroll")
        result = scroll(x=100, y=100, amount=3)

        svc = ready_stack["input_service"]
        svc.scroll.assert_called_once_with(AGENT_X + 100, AGENT_Y + 100, 3, False)

    def test_scroll_horizontal(self, ready_stack):
        scroll = ready_stack["tool"]("Scroll")
        result = scroll(x=100, y=100, amount=-2, horizontal=True)

        svc = ready_stack["input_service"]
        svc.scroll.assert_called_once_with(AGENT_X + 100, AGENT_Y + 100, -2, True)
        assert "horizontally" in result

    def test_scroll_horizontal_string_to_bool(self, ready_stack):
        scroll = ready_stack["tool"]("Scroll")
        scroll(x=100, y=100, horizontal="true")

        svc = ready_stack["input_service"]
        svc.scroll.assert_called_once_with(AGENT_X + 100, AGENT_Y + 100, -3, True)

    def test_scroll_out_of_bounds_returns_error(self, ready_stack):
        scroll = ready_stack["tool"]("Scroll")
        result = scroll(x=5000, y=200)
        assert "Error" in result


# ============================================================================
# TestShortcutE2E
# ============================================================================


class TestShortcutE2E:
    """Shortcut tool end-to-end tests."""

    def test_allowed_shortcut_executes(self, ready_stack):
        shortcut = ready_stack["tool"]("Shortcut")
        result = shortcut(keys="ctrl+c")

        svc = ready_stack["input_service"]
        svc.send_shortcut.assert_called_once_with("ctrl+c")
        assert "Sent shortcut" in result

    def test_blocked_shortcut_alt_tab_returns_error(self, ready_stack):
        """alt+tab is blocked; the real service raises BlockedShortcutError,
        which the guarded_tool decorator catches and returns as an error string."""
        from windowspc_mcp.confinement.errors import BlockedShortcutError

        svc = ready_stack["input_service"]
        svc.send_shortcut.side_effect = BlockedShortcutError(
            "switches the active application focus"
        )

        shortcut = ready_stack["tool"]("Shortcut")
        result = shortcut(keys="alt+tab")
        assert "Error" in result

    def test_blocked_shortcut_win_d_returns_error(self, ready_stack):
        from windowspc_mcp.confinement.errors import BlockedShortcutError

        svc = ready_stack["input_service"]
        svc.send_shortcut.side_effect = BlockedShortcutError(
            "shows/hides the desktop"
        )

        shortcut = ready_stack["tool"]("Shortcut")
        result = shortcut(keys="win+d")
        assert "Error" in result

    def test_allowed_shortcut_f5(self, ready_stack):
        shortcut = ready_stack["tool"]("Shortcut")
        result = shortcut(keys="f5")

        svc = ready_stack["input_service"]
        svc.send_shortcut.assert_called_once_with("f5")

    def test_allowed_shortcut_ctrl_a(self, ready_stack):
        shortcut = ready_stack["tool"]("Shortcut")
        result = shortcut(keys="ctrl+a")

        svc = ready_stack["input_service"]
        svc.send_shortcut.assert_called_once_with("ctrl+a")

    def test_shortcut_not_ready_returns_guard_error(self, ready_stack):
        ready_stack["state_manager"].transition(
            ServerState.DEGRADED, reason="display lost"
        )
        shortcut = ready_stack["tool"]("Shortcut")
        result = shortcut(keys="ctrl+c")
        assert "Cannot use Shortcut" in result


# ============================================================================
# TestWaitE2E
# ============================================================================


class TestWaitE2E:
    """Wait tool end-to-end tests."""

    def test_wait_returns_formatted_message(self, ready_stack):
        wait = ready_stack["tool"]("Wait")
        with patch("windowspc_mcp.tools.input.time.sleep") as mock_sleep:
            result = wait(seconds=1.0)

        assert result == "Waited 1.00s."
        mock_sleep.assert_called_once_with(1.0)

    def test_wait_clamps_low(self, ready_stack):
        wait = ready_stack["tool"]("Wait")
        with patch("windowspc_mcp.tools.input.time.sleep") as mock_sleep:
            result = wait(seconds=0.001)

        assert result == "Waited 0.10s."
        mock_sleep.assert_called_once_with(0.1)

    def test_wait_clamps_high(self, ready_stack):
        wait = ready_stack["tool"]("Wait")
        with patch("windowspc_mcp.tools.input.time.sleep") as mock_sleep:
            result = wait(seconds=999)

        assert result == "Waited 30.00s."
        mock_sleep.assert_called_once_with(30.0)

    def test_wait_zero_clamps_to_minimum(self, ready_stack):
        wait = ready_stack["tool"]("Wait")
        with patch("windowspc_mcp.tools.input.time.sleep") as mock_sleep:
            result = wait(seconds=0)

        assert result == "Waited 0.10s."

    def test_wait_negative_clamps_to_minimum(self, ready_stack):
        wait = ready_stack["tool"]("Wait")
        with patch("windowspc_mcp.tools.input.time.sleep") as mock_sleep:
            result = wait(seconds=-5)

        assert result == "Waited 0.10s."

    def test_wait_exact_boundary_30(self, ready_stack):
        wait = ready_stack["tool"]("Wait")
        with patch("windowspc_mcp.tools.input.time.sleep") as mock_sleep:
            result = wait(seconds=30)

        assert result == "Waited 30.00s."
        mock_sleep.assert_called_once_with(30.0)

    def test_wait_default_1_second(self, ready_stack):
        wait = ready_stack["tool"]("Wait")
        with patch("windowspc_mcp.tools.input.time.sleep") as mock_sleep:
            result = wait()

        assert result == "Waited 1.00s."


# ============================================================================
# TestGuardIntegration
# ============================================================================


class TestGuardIntegration:
    """All input tools are blocked in non-READY states and work in READY."""

    INPUT_TOOLS_WITH_ARGS = {
        "Click": {"x": 100, "y": 200},
        "Type": {"text": "hi", "x": 100, "y": 200},
        "Move": {"x": 100, "y": 200},
        "Scroll": {"x": 100, "y": 200},
        "Shortcut": {"keys": "ctrl+c"},
        "Wait": {"seconds": 0.5},
    }

    def test_all_input_tools_blocked_in_recovering(self, ready_stack):
        ready_stack["state_manager"].transition(ServerState.RECOVERING)

        for name, kwargs in self.INPUT_TOOLS_WITH_ARGS.items():
            tool_fn = ready_stack["tool"](name)
            if name == "Wait":
                with patch("windowspc_mcp.tools.input.time.sleep"):
                    result = tool_fn(**kwargs)
            else:
                result = tool_fn(**kwargs)
            # Wait is UNCONFINED so it should pass even in RECOVERING.
            # All WRITE tools should be blocked.
            if name == "Wait":
                assert "Cannot" not in result, f"Wait should not be blocked in RECOVERING, got: {result}"
            else:
                assert "Cannot" in result, f"{name} should be blocked in RECOVERING, got: {result}"

    def test_all_input_tools_blocked_in_shutting_down(self, ready_stack):
        ready_stack["state_manager"].transition(ServerState.SHUTTING_DOWN)

        for name, kwargs in self.INPUT_TOOLS_WITH_ARGS.items():
            tool_fn = ready_stack["tool"](name)
            if name == "Wait":
                with patch("windowspc_mcp.tools.input.time.sleep"):
                    result = tool_fn(**kwargs)
            else:
                result = tool_fn(**kwargs)
            # ALL tools blocked in SHUTTING_DOWN (guard returns error for all)
            assert "shutting down" in result.lower() or "Cannot" in result, (
                f"{name} should be blocked in SHUTTING_DOWN, got: {result}"
            )

    def test_all_input_tools_blocked_in_degraded(self, ready_stack):
        ready_stack["state_manager"].transition(
            ServerState.DEGRADED, reason="display lost"
        )

        for name, kwargs in self.INPUT_TOOLS_WITH_ARGS.items():
            tool_fn = ready_stack["tool"](name)
            if name == "Wait":
                with patch("windowspc_mcp.tools.input.time.sleep"):
                    result = tool_fn(**kwargs)
            else:
                result = tool_fn(**kwargs)
            # WRITE tools blocked, Wait (UNCONFINED) should pass
            if name == "Wait":
                assert "Cannot" not in result, f"Wait should not be blocked in DEGRADED, got: {result}"
            else:
                assert "Cannot" in result, f"{name} should be blocked in DEGRADED, got: {result}"

    def test_all_input_tools_work_in_ready(self, ready_stack):
        # State is already READY from fixture
        for name, kwargs in self.INPUT_TOOLS_WITH_ARGS.items():
            tool_fn = ready_stack["tool"](name)
            if name == "Wait":
                with patch("windowspc_mcp.tools.input.time.sleep"):
                    result = tool_fn(**kwargs)
            else:
                result = tool_fn(**kwargs)
            assert "Cannot" not in result, f"{name} should work in READY, got: {result}"
            assert "Error" not in result, f"{name} should not error in READY, got: {result}"

    def test_write_tools_blocked_in_degraded(self, ready_stack):
        ready_stack["state_manager"].transition(
            ServerState.DEGRADED, reason="display destroyed"
        )

        write_tools = ["Click", "Type", "Move", "Scroll", "Shortcut"]
        for name in write_tools:
            kwargs = self.INPUT_TOOLS_WITH_ARGS[name]
            tool_fn = ready_stack["tool"](name)
            result = tool_fn(**kwargs)
            assert "Cannot" in result, f"{name} should be blocked in DEGRADED, got: {result}"
