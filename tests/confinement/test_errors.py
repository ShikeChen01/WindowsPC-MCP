"""Tests for windowspc_mcp.confinement.errors — error hierarchy classes."""

import pytest

from windowspc_mcp.confinement.errors import (
    BlockedShortcutError,
    ConfinementError,
    DisplayUnavailableError,
    InvalidStateError,
    TargetNotFoundError,
    WindowsMCPError,
)


# ---------------------------------------------------------------------------
# Hierarchy
# ---------------------------------------------------------------------------


class TestErrorHierarchy:
    def test_windows_mcp_error_is_exception(self):
        assert issubclass(WindowsMCPError, Exception)

    def test_confinement_error_is_windows_mcp_error(self):
        assert issubclass(ConfinementError, WindowsMCPError)

    def test_invalid_state_error_is_windows_mcp_error(self):
        assert issubclass(InvalidStateError, WindowsMCPError)

    def test_blocked_shortcut_error_is_windows_mcp_error(self):
        assert issubclass(BlockedShortcutError, WindowsMCPError)

    def test_display_unavailable_error_is_windows_mcp_error(self):
        assert issubclass(DisplayUnavailableError, WindowsMCPError)

    def test_target_not_found_error_is_windows_mcp_error(self):
        assert issubclass(TargetNotFoundError, WindowsMCPError)


# ---------------------------------------------------------------------------
# Instantiation and message
# ---------------------------------------------------------------------------


class TestErrorMessages:
    def test_windows_mcp_error_message(self):
        err = WindowsMCPError("base error")
        assert str(err) == "base error"

    def test_confinement_error_message(self):
        err = ConfinementError("out of bounds")
        assert str(err) == "out of bounds"

    def test_invalid_state_error_message(self):
        err = InvalidStateError("not ready")
        assert str(err) == "not ready"

    def test_blocked_shortcut_error_message(self):
        err = BlockedShortcutError("alt+tab")
        assert str(err) == "alt+tab"

    def test_display_unavailable_error_message(self):
        err = DisplayUnavailableError("no display")
        assert str(err) == "no display"

    def test_target_not_found_error_message(self):
        err = TargetNotFoundError("button missing")
        assert str(err) == "button missing"


# ---------------------------------------------------------------------------
# Catching with base class
# ---------------------------------------------------------------------------


class TestCatchingWithBaseClass:
    def test_catch_confinement_as_windowsmcp(self):
        with pytest.raises(WindowsMCPError):
            raise ConfinementError("test")

    def test_catch_invalid_state_as_windowsmcp(self):
        with pytest.raises(WindowsMCPError):
            raise InvalidStateError("test")

    def test_catch_blocked_shortcut_as_windowsmcp(self):
        with pytest.raises(WindowsMCPError):
            raise BlockedShortcutError("test")

    def test_catch_display_unavailable_as_windowsmcp(self):
        with pytest.raises(WindowsMCPError):
            raise DisplayUnavailableError("test")

    def test_catch_target_not_found_as_windowsmcp(self):
        with pytest.raises(WindowsMCPError):
            raise TargetNotFoundError("test")


# ---------------------------------------------------------------------------
# Not catching unrelated exceptions
# ---------------------------------------------------------------------------


class TestNotCatchingUnrelated:
    def test_value_error_not_caught_as_windowsmcp(self):
        with pytest.raises(ValueError):
            try:
                raise ValueError("nope")
            except WindowsMCPError:
                pytest.fail("ValueError should not be caught as WindowsMCPError")
            else:
                raise  # re-raise if not caught

    def test_runtime_error_not_caught_as_windowsmcp(self):
        with pytest.raises(RuntimeError):
            try:
                raise RuntimeError("nope")
            except WindowsMCPError:
                pytest.fail("RuntimeError should not be caught as WindowsMCPError")
            else:
                raise


# ---------------------------------------------------------------------------
# Empty messages
# ---------------------------------------------------------------------------


class TestEmptyMessages:
    def test_no_args(self):
        err = WindowsMCPError()
        assert str(err) == ""

    def test_confinement_no_args(self):
        err = ConfinementError()
        assert str(err) == ""
