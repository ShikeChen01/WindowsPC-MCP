"""Tests for windowspc_mcp.uia.patterns — element retrieval and pattern helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ===================================================================
# _get_uia helper
# ===================================================================


class TestGetUia:
    """_get_uia() — internal helper returning IUIAutomation interface."""

    def test_returns_uia_from_singleton(self):
        mock_client = MagicMock()
        mock_client.uia = MagicMock(name="IUIAutomation")

        with patch("windowspc_mcp.uia.core.get_automation_client", return_value=mock_client):
            from windowspc_mcp.uia.patterns import _get_uia
            result = _get_uia()
            assert result is mock_client.uia


# ===================================================================
# Element retrieval
# ===================================================================


class TestGetElementFromPoint:
    """get_element_from_point — retrieve element at screen coordinates."""

    def test_returns_element_on_success(self):
        mock_element = MagicMock(name="UIElement")
        mock_uia = MagicMock()
        mock_uia.ElementFromPoint.return_value = mock_element

        with patch("windowspc_mcp.uia.patterns._get_uia", return_value=mock_uia):
            from windowspc_mcp.uia.patterns import get_element_from_point
            result = get_element_from_point(100, 200)

        assert result is mock_element
        mock_uia.ElementFromPoint.assert_called_once()
        # Verify the POINT struct was passed with correct values
        point_arg = mock_uia.ElementFromPoint.call_args[0][0]
        assert point_arg.x == 100
        assert point_arg.y == 200

    def test_returns_none_when_uia_unavailable(self):
        with patch("windowspc_mcp.uia.patterns._get_uia", return_value=None):
            from windowspc_mcp.uia.patterns import get_element_from_point
            result = get_element_from_point(100, 200)

        assert result is None

    def test_returns_none_on_exception(self):
        mock_uia = MagicMock()
        mock_uia.ElementFromPoint.side_effect = RuntimeError("COM error")

        with patch("windowspc_mcp.uia.patterns._get_uia", return_value=mock_uia):
            from windowspc_mcp.uia.patterns import get_element_from_point
            result = get_element_from_point(100, 200)

        assert result is None


class TestGetElementFromHandle:
    """get_element_from_handle — retrieve element from HWND."""

    def test_returns_element_on_success(self):
        mock_element = MagicMock(name="UIElement")
        mock_uia = MagicMock()
        mock_uia.ElementFromHandle.return_value = mock_element

        with patch("windowspc_mcp.uia.patterns._get_uia", return_value=mock_uia):
            from windowspc_mcp.uia.patterns import get_element_from_handle
            result = get_element_from_handle(42)

        assert result is mock_element
        mock_uia.ElementFromHandle.assert_called_once_with(42)

    def test_returns_none_when_uia_unavailable(self):
        with patch("windowspc_mcp.uia.patterns._get_uia", return_value=None):
            from windowspc_mcp.uia.patterns import get_element_from_handle
            result = get_element_from_handle(42)

        assert result is None

    def test_returns_none_on_exception(self):
        mock_uia = MagicMock()
        mock_uia.ElementFromHandle.side_effect = OSError("handle invalid")

        with patch("windowspc_mcp.uia.patterns._get_uia", return_value=mock_uia):
            from windowspc_mcp.uia.patterns import get_element_from_handle
            result = get_element_from_handle(42)

        assert result is None


# ===================================================================
# Element property helpers
# ===================================================================


class TestGetElementRect:
    """get_element_rect — bounding rectangle extraction."""

    def test_returns_rect_tuple(self):
        mock_rect = MagicMock()
        mock_rect.left = 10
        mock_rect.top = 20
        mock_rect.right = 310
        mock_rect.bottom = 220

        mock_element = MagicMock()
        mock_element.CurrentBoundingRectangle = mock_rect

        from windowspc_mcp.uia.patterns import get_element_rect
        result = get_element_rect(mock_element)
        assert result == (10, 20, 310, 220)

    def test_returns_none_when_element_is_none(self):
        from windowspc_mcp.uia.patterns import get_element_rect
        result = get_element_rect(None)
        assert result is None

    def test_returns_none_on_exception(self):
        mock_element = MagicMock()
        type(mock_element).CurrentBoundingRectangle = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("disconnected"))
        )

        from windowspc_mcp.uia.patterns import get_element_rect
        result = get_element_rect(mock_element)
        assert result is None


# ===================================================================
# Pattern helpers — InvokePattern
# ===================================================================


class TestTryInvoke:
    """try_invoke — InvokePattern (pattern ID 10000)."""

    def test_success(self):
        mock_pattern = MagicMock()
        mock_pattern.QueryInterface.return_value = mock_pattern

        mock_element = MagicMock()
        mock_element.GetCurrentPattern.return_value = mock_pattern

        from windowspc_mcp.uia.patterns import try_invoke
        result = try_invoke(mock_element)

        assert result is True
        mock_element.GetCurrentPattern.assert_called_once_with(10000)
        mock_pattern.QueryInterface.assert_called_once()
        mock_pattern.Invoke.assert_called_once()

    def test_returns_false_when_element_is_none(self):
        from windowspc_mcp.uia.patterns import try_invoke
        assert try_invoke(None) is False

    def test_returns_false_when_pattern_is_none(self):
        mock_element = MagicMock()
        mock_element.GetCurrentPattern.return_value = None

        from windowspc_mcp.uia.patterns import try_invoke
        result = try_invoke(mock_element)
        assert result is False

    def test_returns_false_on_exception(self):
        mock_element = MagicMock()
        mock_element.GetCurrentPattern.side_effect = RuntimeError("COM error")

        from windowspc_mcp.uia.patterns import try_invoke
        result = try_invoke(mock_element)
        assert result is False

    def test_returns_false_on_invoke_exception(self):
        """Exception during Invoke() itself is caught."""
        mock_pattern = MagicMock()
        mock_qi = MagicMock()
        mock_qi.Invoke.side_effect = RuntimeError("invoke failed")
        mock_pattern.QueryInterface.return_value = mock_qi

        mock_element = MagicMock()
        mock_element.GetCurrentPattern.return_value = mock_pattern

        from windowspc_mcp.uia.patterns import try_invoke
        result = try_invoke(mock_element)
        assert result is False

    def test_query_interface_uses_pattern_type(self):
        """QueryInterface is called with type(pattern) as argument."""
        mock_pattern = MagicMock()
        mock_pattern.QueryInterface.return_value = mock_pattern

        mock_element = MagicMock()
        mock_element.GetCurrentPattern.return_value = mock_pattern

        from windowspc_mcp.uia.patterns import try_invoke
        try_invoke(mock_element)

        mock_pattern.QueryInterface.assert_called_once_with(type(mock_pattern))


# ===================================================================
# Pattern helpers — ValuePattern
# ===================================================================


class TestTrySetValue:
    """try_set_value — ValuePattern (pattern ID 10002)."""

    def test_success(self):
        mock_pattern = MagicMock()
        mock_pattern.QueryInterface.return_value = mock_pattern

        mock_element = MagicMock()
        mock_element.GetCurrentPattern.return_value = mock_pattern

        from windowspc_mcp.uia.patterns import try_set_value
        result = try_set_value(mock_element, "hello")

        assert result is True
        mock_element.GetCurrentPattern.assert_called_once_with(10002)
        mock_pattern.SetValue.assert_called_once_with("hello")

    def test_returns_false_when_element_is_none(self):
        from windowspc_mcp.uia.patterns import try_set_value
        assert try_set_value(None, "x") is False

    def test_returns_false_when_pattern_is_none(self):
        mock_element = MagicMock()
        mock_element.GetCurrentPattern.return_value = None

        from windowspc_mcp.uia.patterns import try_set_value
        result = try_set_value(mock_element, "x")
        assert result is False

    def test_returns_false_on_exception(self):
        mock_element = MagicMock()
        mock_element.GetCurrentPattern.side_effect = RuntimeError("COM error")

        from windowspc_mcp.uia.patterns import try_set_value
        result = try_set_value(mock_element, "x")
        assert result is False

    def test_returns_false_on_set_value_exception(self):
        """Exception during SetValue() itself is caught."""
        mock_pattern = MagicMock()
        mock_qi = MagicMock()
        mock_qi.SetValue.side_effect = RuntimeError("read-only")
        mock_pattern.QueryInterface.return_value = mock_qi

        mock_element = MagicMock()
        mock_element.GetCurrentPattern.return_value = mock_pattern

        from windowspc_mcp.uia.patterns import try_set_value
        result = try_set_value(mock_element, "hello")
        assert result is False

    def test_empty_string_value(self):
        """Setting an empty string should still succeed."""
        mock_pattern = MagicMock()
        mock_pattern.QueryInterface.return_value = mock_pattern

        mock_element = MagicMock()
        mock_element.GetCurrentPattern.return_value = mock_pattern

        from windowspc_mcp.uia.patterns import try_set_value
        result = try_set_value(mock_element, "")

        assert result is True
        mock_pattern.SetValue.assert_called_once_with("")

    def test_query_interface_uses_pattern_type(self):
        """QueryInterface is called with type(pattern) as argument."""
        mock_pattern = MagicMock()
        mock_pattern.QueryInterface.return_value = mock_pattern

        mock_element = MagicMock()
        mock_element.GetCurrentPattern.return_value = mock_pattern

        from windowspc_mcp.uia.patterns import try_set_value
        try_set_value(mock_element, "val")

        mock_pattern.QueryInterface.assert_called_once_with(type(mock_pattern))


# ===================================================================
# UIA Pattern ID constants
# ===================================================================


class TestPatternConstants:
    """Pattern ID constants match UIAutomation spec."""

    def test_invoke_pattern_id(self):
        from windowspc_mcp.uia.patterns import UIA_InvokePatternId
        assert UIA_InvokePatternId == 10000

    def test_value_pattern_id(self):
        from windowspc_mcp.uia.patterns import UIA_ValuePatternId
        assert UIA_ValuePatternId == 10002
