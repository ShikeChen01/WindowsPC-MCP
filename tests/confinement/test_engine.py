"""Tests for windowspc_mcp.confinement.engine — ConfinementEngine and ScreenBounds."""

import threading

import pytest

from windowspc_mcp.confinement.engine import (
    ActionType,
    ConfinementEngine,
    ScreenBounds,
    _TOOL_ACTIONS,
)
from windowspc_mcp.confinement.errors import ConfinementError
from tests.conftest import MockBounds


# ---------------------------------------------------------------------------
# ScreenBounds dataclass
# ---------------------------------------------------------------------------


class TestScreenBounds:
    def test_basic_properties(self):
        b = ScreenBounds(x=100, y=200, width=800, height=600)
        assert b.left == 100
        assert b.top == 200
        assert b.right == 900
        assert b.bottom == 800

    def test_zero_origin(self):
        b = ScreenBounds(x=0, y=0, width=1920, height=1080)
        assert b.left == 0
        assert b.top == 0
        assert b.right == 1920
        assert b.bottom == 1080


# ---------------------------------------------------------------------------
# set_agent_bounds / clear_bounds
# ---------------------------------------------------------------------------


class TestSetAgentBounds:
    def test_sets_bounds_from_any_object_with_attrs(self):
        engine = ConfinementEngine()
        engine.set_agent_bounds(MockBounds(x=100, y=50, width=800, height=600))
        assert engine.bounds is not None
        assert engine.bounds.x == 100
        assert engine.bounds.y == 50
        assert engine.bounds.width == 800
        assert engine.bounds.height == 600

    def test_overwrites_previous_bounds(self):
        engine = ConfinementEngine()
        engine.set_agent_bounds(MockBounds(x=0, y=0, width=1920, height=1080))
        engine.set_agent_bounds(MockBounds(x=3840, y=0, width=1920, height=1080))
        assert engine.bounds.x == 3840


class TestClearBounds:
    def test_clears_existing_bounds(self):
        engine = ConfinementEngine()
        engine.set_agent_bounds(MockBounds())
        assert engine.bounds is not None
        engine.clear_bounds()
        assert engine.bounds is None

    def test_clear_when_already_none_is_idempotent(self):
        engine = ConfinementEngine()
        assert engine.bounds is None
        engine.clear_bounds()
        assert engine.bounds is None


# ---------------------------------------------------------------------------
# classify_action — every tool in _TOOL_ACTIONS + unknown
# ---------------------------------------------------------------------------


class TestClassifyActionReadTools:
    @pytest.mark.parametrize("tool", ["Screenshot", "Snapshot", "Scrape", "ScreenInfo"])
    def test_read_tools(self, tool):
        engine = ConfinementEngine()
        assert engine.classify_action(tool) == ActionType.READ


class TestClassifyActionWriteTools:
    @pytest.mark.parametrize(
        "tool",
        [
            "Click",
            "Type",
            "Move",
            "Scroll",
            "Shortcut",
            "App",
            "MultiSelect",
            "MultiEdit",
            "RecoverWindow",
        ],
    )
    def test_write_tools(self, tool):
        engine = ConfinementEngine()
        assert engine.classify_action(tool) == ActionType.WRITE


class TestClassifyActionUnconfinedTools:
    @pytest.mark.parametrize(
        "tool",
        [
            "Wait",
            "Notification",
            "PowerShell",
            "FileSystem",
            "Clipboard",
            "Process",
            "Registry",
            "CreateScreen",
            "DestroyScreen",
        ],
    )
    def test_unconfined_tools(self, tool):
        engine = ConfinementEngine()
        assert engine.classify_action(tool) == ActionType.UNCONFINED


class TestClassifyActionUnknown:
    def test_unknown_tool_defaults_to_unconfined(self):
        engine = ConfinementEngine()
        assert engine.classify_action("FooBar") == ActionType.UNCONFINED

    def test_empty_string_defaults_to_unconfined(self):
        engine = ConfinementEngine()
        assert engine.classify_action("") == ActionType.UNCONFINED


class TestClassifyActionExhaustive:
    """Verify every entry in _TOOL_ACTIONS is actually reachable."""

    def test_all_registered_tools_covered(self):
        engine = ConfinementEngine()
        for tool_name, expected in _TOOL_ACTIONS.items():
            assert engine.classify_action(tool_name) == expected


# ---------------------------------------------------------------------------
# validate_and_translate — all boundary conditions
# ---------------------------------------------------------------------------


@pytest.fixture
def engine():
    e = ConfinementEngine()
    e.set_agent_bounds(MockBounds(x=3840, y=0, width=1920, height=1080))
    return e


class TestValidateAndTranslateSuccess:
    def test_origin(self, engine):
        assert engine.validate_and_translate(0, 0) == (3840, 0)

    def test_center(self, engine):
        assert engine.validate_and_translate(960, 540) == (4800, 540)

    def test_max_valid_x(self, engine):
        assert engine.validate_and_translate(1919, 0) == (5759, 0)

    def test_max_valid_y(self, engine):
        assert engine.validate_and_translate(0, 1079) == (3840, 1079)

    def test_max_valid_corner(self, engine):
        assert engine.validate_and_translate(1919, 1079) == (5759, 1079)


class TestValidateAndTranslateErrors:
    def test_no_bounds_raises(self):
        engine = ConfinementEngine()
        with pytest.raises(ConfinementError, match="no agent display"):
            engine.validate_and_translate(0, 0)

    def test_negative_x(self, engine):
        with pytest.raises(ConfinementError, match="out of bounds"):
            engine.validate_and_translate(-1, 0)

    def test_negative_y(self, engine):
        with pytest.raises(ConfinementError, match="out of bounds"):
            engine.validate_and_translate(0, -1)

    def test_x_equals_width(self, engine):
        with pytest.raises(ConfinementError, match="out of bounds"):
            engine.validate_and_translate(1920, 0)

    def test_y_equals_height(self, engine):
        with pytest.raises(ConfinementError, match="out of bounds"):
            engine.validate_and_translate(0, 1080)

    def test_both_negative(self, engine):
        with pytest.raises(ConfinementError, match="out of bounds"):
            engine.validate_and_translate(-5, -5)

    def test_both_over_max(self, engine):
        with pytest.raises(ConfinementError, match="out of bounds"):
            engine.validate_and_translate(2000, 2000)

    def test_error_message_includes_coordinates(self, engine):
        with pytest.raises(ConfinementError, match=r"coordinate \(2000, 500\)"):
            engine.validate_and_translate(2000, 500)

    def test_error_message_includes_valid_range(self, engine):
        with pytest.raises(ConfinementError, match=r"x=\[0, 1919\].*y=\[0, 1079\]"):
            engine.validate_and_translate(2000, 2000)


class TestValidateAndTranslateRelYEdgeCases:
    """Specific edge cases around rel_y boundaries."""

    def test_rel_y_zero(self, engine):
        abs_x, abs_y = engine.validate_and_translate(0, 0)
        assert abs_y == 0

    def test_rel_y_one(self, engine):
        _, abs_y = engine.validate_and_translate(0, 1)
        assert abs_y == 1

    def test_rel_y_max_minus_one(self, engine):
        _, abs_y = engine.validate_and_translate(0, 1078)
        assert abs_y == 1078

    def test_rel_y_max_valid(self, engine):
        _, abs_y = engine.validate_and_translate(0, 1079)
        assert abs_y == 1079

    def test_rel_y_at_height_boundary_raises(self, engine):
        with pytest.raises(ConfinementError):
            engine.validate_and_translate(0, 1080)

    def test_rel_y_one_past_height_raises(self, engine):
        with pytest.raises(ConfinementError):
            engine.validate_and_translate(0, 1081)

    def test_nonzero_y_origin_translates_correctly(self):
        """When the agent screen starts at y=200, translations add that offset."""
        engine = ConfinementEngine()
        engine.set_agent_bounds(MockBounds(x=0, y=200, width=800, height=600))
        _, abs_y = engine.validate_and_translate(0, 0)
        assert abs_y == 200
        _, abs_y = engine.validate_and_translate(0, 599)
        assert abs_y == 799


# ---------------------------------------------------------------------------
# is_point_on_agent_screen
# ---------------------------------------------------------------------------


class TestIsPointOnAgentScreen:
    def test_no_bounds_returns_false(self):
        engine = ConfinementEngine()
        assert engine.is_point_on_agent_screen(100, 100) is False

    def test_inside_bounds(self, engine):
        assert engine.is_point_on_agent_screen(4000, 500) is True

    def test_on_left_edge(self, engine):
        assert engine.is_point_on_agent_screen(3840, 0) is True

    def test_on_top_edge(self, engine):
        assert engine.is_point_on_agent_screen(3840, 0) is True

    def test_on_right_boundary_exclusive(self, engine):
        # right = 3840 + 1920 = 5760, so x=5760 is OUT
        assert engine.is_point_on_agent_screen(5760, 0) is False

    def test_on_bottom_boundary_exclusive(self, engine):
        # bottom = 0 + 1080 = 1080, so y=1080 is OUT
        assert engine.is_point_on_agent_screen(3840, 1080) is False

    def test_just_inside_right_edge(self, engine):
        assert engine.is_point_on_agent_screen(5759, 0) is True

    def test_just_inside_bottom_edge(self, engine):
        assert engine.is_point_on_agent_screen(3840, 1079) is True

    def test_outside_left(self, engine):
        assert engine.is_point_on_agent_screen(3839, 500) is False

    def test_outside_above(self, engine):
        engine2 = ConfinementEngine()
        engine2.set_agent_bounds(MockBounds(x=0, y=100, width=800, height=600))
        assert engine2.is_point_on_agent_screen(400, 99) is False

    def test_far_outside(self, engine):
        assert engine.is_point_on_agent_screen(0, 0) is False


# ---------------------------------------------------------------------------
# validate_absolute_point
# ---------------------------------------------------------------------------


class TestValidateAbsolutePoint:
    def test_no_bounds_raises(self):
        engine = ConfinementEngine()
        with pytest.raises(ConfinementError, match="no agent display assigned"):
            engine.validate_absolute_point(100, 100)

    def test_inside_bounds_passes(self, engine):
        engine.validate_absolute_point(4000, 500)  # should not raise

    def test_on_left_boundary_passes(self, engine):
        engine.validate_absolute_point(3840, 0)  # should not raise

    def test_at_max_valid_corner_passes(self, engine):
        engine.validate_absolute_point(5759, 1079)  # should not raise

    def test_outside_bounds_raises_with_range(self, engine):
        with pytest.raises(ConfinementError, match="not on the agent screen"):
            engine.validate_absolute_point(100, 500)

    def test_error_includes_coordinates(self, engine):
        with pytest.raises(ConfinementError, match=r"absolute point \(100, 500\)"):
            engine.validate_absolute_point(100, 500)


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


class TestThreadSafety:
    def test_concurrent_set_and_validate(self):
        """Multiple threads setting bounds and validating concurrently should not crash."""
        engine = ConfinementEngine()
        errors = []

        def writer(x_offset):
            try:
                for _ in range(200):
                    engine.set_agent_bounds(
                        MockBounds(x=x_offset, y=0, width=1920, height=1080)
                    )
            except Exception as exc:
                errors.append(exc)

        def reader():
            try:
                for _ in range(200):
                    try:
                        engine.validate_and_translate(100, 100)
                    except ConfinementError:
                        pass  # bounds may be None between sets
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(i * 1920,)) for i in range(3)]
        threads.append(threading.Thread(target=reader))
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread safety errors: {errors}"

    def test_concurrent_clear_and_is_point(self):
        engine = ConfinementEngine()
        engine.set_agent_bounds(MockBounds())
        errors = []

        def toggler():
            try:
                for _ in range(200):
                    engine.set_agent_bounds(MockBounds())
                    engine.clear_bounds()
            except Exception as exc:
                errors.append(exc)

        def checker():
            try:
                for _ in range(200):
                    engine.is_point_on_agent_screen(4000, 500)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=toggler), threading.Thread(target=checker)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
