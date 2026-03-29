"""Tests for windowspc_mcp.confinement.decorators — guarded_tool and with_tool_name."""

from unittest.mock import MagicMock

import pytest

from windowspc_mcp.confinement.decorators import guarded_tool, with_tool_name
from windowspc_mcp.confinement.errors import (
    BlockedShortcutError,
    ConfinementError,
    DisplayUnavailableError,
    InvalidStateError,
    TargetNotFoundError,
    WindowsMCPError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_guard(return_value=None):
    """Return a mock guard whose .check() returns the given value."""
    mock_guard = MagicMock()
    mock_guard.check.return_value = return_value
    return mock_guard


# ---------------------------------------------------------------------------
# guarded_tool — guard returns None (tool executes normally)
# ---------------------------------------------------------------------------


class TestGuardedToolPassThrough:
    def test_guard_none_allows_execution(self):
        guard = _make_guard(return_value=None)

        @guarded_tool(lambda: guard)
        def my_tool(x, y):
            return f"clicked {x},{y}"

        result = my_tool(10, 20)
        assert result == "clicked 10,20"
        guard.check.assert_called_once_with("my_tool")

    def test_kwargs_forwarded(self):
        guard = _make_guard(return_value=None)

        @guarded_tool(lambda: guard)
        def tool_with_kwargs(name="default"):
            return name

        assert tool_with_kwargs(name="hello") == "hello"

    def test_no_guard_callable_returns_none(self):
        """When get_guard returns None (not callable or returns None), tool runs."""

        @guarded_tool(lambda: None)
        def my_tool():
            return "ok"

        assert my_tool() == "ok"


# ---------------------------------------------------------------------------
# guarded_tool — guard returns error string (tool blocked)
# ---------------------------------------------------------------------------


class TestGuardedToolBlocked:
    def test_guard_error_returned_directly(self):
        guard = _make_guard(return_value="Server is shutting down. No tools available.")

        @guarded_tool(lambda: guard)
        def my_tool():
            return "should not run"

        result = my_tool()
        assert result == "Server is shutting down. No tools available."

    def test_tool_body_not_executed_when_blocked(self):
        guard = _make_guard(return_value="blocked")
        call_tracker = MagicMock()

        @guarded_tool(lambda: guard)
        def my_tool():
            call_tracker()
            return "ran"

        my_tool()
        call_tracker.assert_not_called()


# ---------------------------------------------------------------------------
# guarded_tool — catches WindowsMCPError subclasses
# ---------------------------------------------------------------------------


class TestGuardedToolCatchesErrors:
    def test_catches_confinement_error(self):
        guard = _make_guard(return_value=None)

        @guarded_tool(lambda: guard)
        def my_tool():
            raise ConfinementError("point out of bounds")

        result = my_tool()
        assert "Error:" in result
        assert "point out of bounds" in result

    def test_catches_invalid_state_error(self):
        guard = _make_guard(return_value=None)

        @guarded_tool(lambda: guard)
        def my_tool():
            raise InvalidStateError("not ready")

        result = my_tool()
        assert "Error:" in result
        assert "not ready" in result

    def test_catches_blocked_shortcut_error(self):
        guard = _make_guard(return_value=None)

        @guarded_tool(lambda: guard)
        def my_tool():
            raise BlockedShortcutError("alt+tab is blocked")

        result = my_tool()
        assert "Error:" in result
        assert "alt+tab is blocked" in result

    def test_catches_display_unavailable_error(self):
        guard = _make_guard(return_value=None)

        @guarded_tool(lambda: guard)
        def my_tool():
            raise DisplayUnavailableError("no display")

        result = my_tool()
        assert "Error:" in result
        assert "no display" in result

    def test_catches_target_not_found_error(self):
        guard = _make_guard(return_value=None)

        @guarded_tool(lambda: guard)
        def my_tool():
            raise TargetNotFoundError("button not found")

        result = my_tool()
        assert "Error:" in result
        assert "button not found" in result

    def test_catches_base_windowsmcp_error(self):
        guard = _make_guard(return_value=None)

        @guarded_tool(lambda: guard)
        def my_tool():
            raise WindowsMCPError("generic error")

        result = my_tool()
        assert "Error:" in result
        assert "generic error" in result

    def test_does_not_catch_non_windowsmcp_errors(self):
        guard = _make_guard(return_value=None)

        @guarded_tool(lambda: guard)
        def my_tool():
            raise ValueError("not a WindowsMCPError")

        with pytest.raises(ValueError, match="not a WindowsMCPError"):
            my_tool()


# ---------------------------------------------------------------------------
# with_tool_name — sets _tool_name attribute
# ---------------------------------------------------------------------------


class TestWithToolName:
    def test_sets_tool_name_attribute(self):
        @with_tool_name("Click")
        def click_handler(x, y):
            return f"{x},{y}"

        assert hasattr(click_handler, "_tool_name")
        assert click_handler._tool_name == "Click"

    def test_function_still_callable(self):
        @with_tool_name("Type")
        def type_handler(text):
            return text

        assert type_handler("hello") == "hello"


# ---------------------------------------------------------------------------
# guarded_tool uses _tool_name when present
# ---------------------------------------------------------------------------


class TestGuardedToolUsesToolName:
    def test_guard_check_receives_tool_name(self):
        guard = _make_guard(return_value=None)

        @guarded_tool(lambda: guard)
        @with_tool_name("Click")
        def click_handler(x, y):
            return f"{x},{y}"

        click_handler(10, 20)
        guard.check.assert_called_once_with("Click")

    def test_falls_back_to_func_name_without_tool_name(self):
        guard = _make_guard(return_value=None)

        @guarded_tool(lambda: guard)
        def some_func():
            return "ok"

        some_func()
        guard.check.assert_called_once_with("some_func")


# ---------------------------------------------------------------------------
# functools.wraps preserves metadata
# ---------------------------------------------------------------------------


class TestWrappedMetadata:
    def test_preserves_function_name(self):
        @guarded_tool(lambda: None)
        def my_special_tool():
            """Docstring here."""
            pass

        assert my_special_tool.__name__ == "my_special_tool"
        assert my_special_tool.__doc__ == "Docstring here."
