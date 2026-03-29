"""Tests for windowspc_mcp.uia.core — COM singleton, INPUT structures, SendInput wrapper."""

from __future__ import annotations

import ctypes
import sys
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ---------------------------------------------------------------------------
# We must mock comtypes and ctypes.windll *before* importing core, because
# core.py executes module-level statements that access user32 function
# pointers.  We build a fake user32 object whose attribute accesses always
# return a further MagicMock (mimicking ctypes function-pointer setup).
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_singleton():
    """Reset the _AutomationClient singleton between tests."""
    # Importing may have already created the singleton, so we need to
    # reach in and reset it after each test.
    yield
    from windowspc_mcp.uia.core import _AutomationClient
    _AutomationClient._instance = None


# ===================================================================
# INPUT structures
# ===================================================================


class TestMOUSEINPUT:
    """MOUSEINPUT ctypes Structure."""

    def test_fields_exist(self):
        from windowspc_mcp.uia.core import MOUSEINPUT
        mi = MOUSEINPUT()
        assert hasattr(mi, "dx")
        assert hasattr(mi, "dy")
        assert hasattr(mi, "mouseData")
        assert hasattr(mi, "dwFlags")
        assert hasattr(mi, "time")
        assert hasattr(mi, "dwExtraInfo")

    def test_field_values(self):
        from windowspc_mcp.uia.core import MOUSEINPUT
        mi = MOUSEINPUT(dx=100, dy=200, mouseData=120, dwFlags=0x0002, time=0, dwExtraInfo=None)
        assert mi.dx == 100
        assert mi.dy == 200
        assert mi.mouseData == 120
        assert mi.dwFlags == 0x0002


class TestKEYBDINPUT:
    """KEYBDINPUT ctypes Structure."""

    def test_fields_exist(self):
        from windowspc_mcp.uia.core import KEYBDINPUT
        ki = KEYBDINPUT()
        assert hasattr(ki, "wVk")
        assert hasattr(ki, "wScan")
        assert hasattr(ki, "dwFlags")
        assert hasattr(ki, "time")
        assert hasattr(ki, "dwExtraInfo")

    def test_field_values(self):
        from windowspc_mcp.uia.core import KEYBDINPUT
        ki = KEYBDINPUT(wVk=0, wScan=65, dwFlags=0x0004, time=0, dwExtraInfo=None)
        assert ki.wVk == 0
        assert ki.wScan == 65
        assert ki.dwFlags == 0x0004


class TestINPUTUnionAndStruct:
    """INPUT_UNION and INPUT wrapper structures."""

    def test_input_union_mouse(self):
        from windowspc_mcp.uia.core import INPUT_UNION, MOUSEINPUT
        mi = MOUSEINPUT(dx=10, dy=20)
        u = INPUT_UNION(mi=mi)
        assert u.mi.dx == 10
        assert u.mi.dy == 20

    def test_input_union_keyboard(self):
        from windowspc_mcp.uia.core import INPUT_UNION, KEYBDINPUT
        ki = KEYBDINPUT(wVk=0, wScan=97)
        u = INPUT_UNION(ki=ki)
        assert u.ki.wScan == 97

    def test_input_struct_mouse_type(self):
        from windowspc_mcp.uia.core import INPUT, INPUT_UNION, MOUSEINPUT, INPUT_MOUSE
        mi = MOUSEINPUT(dx=5, dy=6)
        inp = INPUT(type=INPUT_MOUSE, _input=INPUT_UNION(mi=mi))
        assert inp.type == INPUT_MOUSE
        assert inp._input.mi.dx == 5

    def test_input_struct_keyboard_type(self):
        from windowspc_mcp.uia.core import INPUT, INPUT_UNION, KEYBDINPUT, INPUT_KEYBOARD
        ki = KEYBDINPUT(wScan=66, dwFlags=0x0004)
        inp = INPUT(type=INPUT_KEYBOARD, _input=INPUT_UNION(ki=ki))
        assert inp.type == INPUT_KEYBOARD
        assert inp._input.ki.wScan == 66


# ===================================================================
# Constants
# ===================================================================


class TestConstants:
    """Module-level constants are exported with correct values."""

    def test_input_type_constants(self):
        from windowspc_mcp.uia.core import INPUT_MOUSE, INPUT_KEYBOARD
        assert INPUT_MOUSE == 0
        assert INPUT_KEYBOARD == 1

    def test_mouse_event_flags(self):
        from windowspc_mcp.uia.core import (
            MOUSEEVENTF_MOVE,
            MOUSEEVENTF_LEFTDOWN,
            MOUSEEVENTF_LEFTUP,
            MOUSEEVENTF_RIGHTDOWN,
            MOUSEEVENTF_RIGHTUP,
            MOUSEEVENTF_MIDDLEDOWN,
            MOUSEEVENTF_MIDDLEUP,
            MOUSEEVENTF_WHEEL,
            MOUSEEVENTF_ABSOLUTE,
        )
        assert MOUSEEVENTF_MOVE == 0x0001
        assert MOUSEEVENTF_LEFTDOWN == 0x0002
        assert MOUSEEVENTF_LEFTUP == 0x0004
        assert MOUSEEVENTF_RIGHTDOWN == 0x0008
        assert MOUSEEVENTF_RIGHTUP == 0x0010
        assert MOUSEEVENTF_MIDDLEDOWN == 0x0020
        assert MOUSEEVENTF_MIDDLEUP == 0x0040
        assert MOUSEEVENTF_WHEEL == 0x0800
        assert MOUSEEVENTF_ABSOLUTE == 0x8000

    def test_key_event_flags(self):
        from windowspc_mcp.uia.core import KEYEVENTF_UNICODE, KEYEVENTF_KEYUP
        assert KEYEVENTF_UNICODE == 0x0004
        assert KEYEVENTF_KEYUP == 0x0002

    def test_window_constants(self):
        from windowspc_mcp.uia.core import SW_RESTORE, GA_ROOT
        assert SW_RESTORE == 9
        assert GA_ROOT == 2


# ===================================================================
# send_input wrapper
# ===================================================================


class TestSendInput:
    """send_input() — wraps user32.SendInput."""

    def test_calls_user32_sendinput_with_correct_count(self):
        from windowspc_mcp.uia.core import send_input, INPUT, INPUT_UNION, MOUSEINPUT, INPUT_MOUSE
        mi = MOUSEINPUT(dx=0, dy=0)
        inp1 = INPUT(type=INPUT_MOUSE, _input=INPUT_UNION(mi=mi))
        inp2 = INPUT(type=INPUT_MOUSE, _input=INPUT_UNION(mi=mi))

        with patch.object(
            ctypes.windll.user32, "SendInput", return_value=2
        ) as mock_si:
            result = send_input(inp1, inp2)

        assert result == 2
        mock_si.assert_called_once()
        args = mock_si.call_args
        assert args[0][0] == 2  # nInputs

    def test_single_input(self):
        from windowspc_mcp.uia.core import send_input, INPUT, INPUT_UNION, KEYBDINPUT, INPUT_KEYBOARD
        ki = KEYBDINPUT(wScan=65, dwFlags=0x0004)
        inp = INPUT(type=INPUT_KEYBOARD, _input=INPUT_UNION(ki=ki))

        with patch.object(
            ctypes.windll.user32, "SendInput", return_value=1
        ) as mock_si:
            result = send_input(inp)

        assert result == 1
        args = mock_si.call_args
        assert args[0][0] == 1

    def test_empty_inputs(self):
        """Calling send_input with no arguments creates a 0-length array."""
        with patch.object(
            ctypes.windll.user32, "SendInput", return_value=0
        ) as mock_si:
            from windowspc_mcp.uia.core import send_input
            result = send_input()

        assert result == 0
        args = mock_si.call_args
        assert args[0][0] == 0


# ===================================================================
# _AutomationClient singleton
# ===================================================================


class TestAutomationClientSingleton:
    """_AutomationClient — singleton pattern and COM initialization."""

    def test_singleton_returns_same_instance(self):
        from windowspc_mcp.uia.core import _AutomationClient

        with patch.object(_AutomationClient, "_init_com"):
            a = _AutomationClient()
            b = _AutomationClient()
            assert a is b

    def test_init_com_called_once(self):
        from windowspc_mcp.uia.core import _AutomationClient

        with patch.object(_AutomationClient, "_init_com") as mock_init:
            _AutomationClient()
            _AutomationClient()
            mock_init.assert_called_once()

    def test_init_com_success(self):
        """Successful COM initialization sets _uia and _walker."""
        from windowspc_mcp.uia.core import _AutomationClient

        mock_uia_dll = MagicMock()
        mock_uia_obj = MagicMock()
        mock_walker = MagicMock()
        mock_uia_obj.RawViewWalker = mock_walker

        with patch.dict(sys.modules, {
            "comtypes": MagicMock(),
            "comtypes.client": MagicMock(),
        }):
            import comtypes
            import comtypes.client

            comtypes.client.GetModule.return_value = mock_uia_dll
            comtypes.client.CreateObject.return_value = mock_uia_obj

            client = _AutomationClient()
            # Force _init_com to actually run by resetting
            client._initialized = False
            client._uia = None
            client._walker = None
            client._init_com()

            assert client._uia is mock_uia_obj
            assert client._walker is mock_walker

    def test_init_com_retries_on_failure(self):
        """_init_com retries up to 3 times."""
        from windowspc_mcp.uia.core import _AutomationClient

        with patch.object(_AutomationClient, "_init_com"):
            client = _AutomationClient()

        with patch.dict(sys.modules, {
            "comtypes": MagicMock(),
            "comtypes.client": MagicMock(),
        }):
            import comtypes.client

            comtypes.client.GetModule.side_effect = RuntimeError("COM failure")

            client._uia = None
            client._walker = None

            with patch("time.sleep"):
                client._init_com()

            # GetModule called 3 times (retries)
            assert comtypes.client.GetModule.call_count == 3
            assert client._uia is None

    def test_init_com_oserror_on_coinitialize_ignored(self):
        """OSError from CoInitializeEx is silently ignored (already init)."""
        from windowspc_mcp.uia.core import _AutomationClient

        mock_uia_dll = MagicMock()
        mock_uia_obj = MagicMock()
        mock_uia_obj.RawViewWalker = MagicMock()

        with patch.dict(sys.modules, {
            "comtypes": MagicMock(),
            "comtypes.client": MagicMock(),
        }):
            import comtypes
            import comtypes.client

            comtypes.CoInitializeEx.side_effect = OSError("already initialized")
            comtypes.client.GetModule.return_value = mock_uia_dll
            comtypes.client.CreateObject.return_value = mock_uia_obj

            client = _AutomationClient()
            client._initialized = False
            client._uia = None
            client._walker = None
            client._init_com()

            # Should still succeed despite OSError
            assert client._uia is mock_uia_obj

    def test_uia_property_reinitializes_if_none(self):
        """uia property calls _init_com when _uia is None."""
        from windowspc_mcp.uia.core import _AutomationClient

        with patch.object(_AutomationClient, "_init_com"):
            client = _AutomationClient()
            client._uia = None

            with patch.object(_AutomationClient, "_init_com") as mock_init:
                _ = client.uia
                mock_init.assert_called_once()

    def test_uia_property_skips_init_if_set(self):
        """uia property does NOT re-init if _uia is already set."""
        from windowspc_mcp.uia.core import _AutomationClient

        sentinel = object()
        with patch.object(_AutomationClient, "_init_com"):
            client = _AutomationClient()
            client._uia = sentinel

        with patch.object(_AutomationClient, "_init_com") as mock_init:
            result = client.uia
            mock_init.assert_not_called()
            assert result is sentinel

    def test_walker_property_reinitializes_if_none(self):
        """walker property calls _init_com when _walker is None."""
        from windowspc_mcp.uia.core import _AutomationClient

        with patch.object(_AutomationClient, "_init_com"):
            client = _AutomationClient()
            client._walker = None

        with patch.object(_AutomationClient, "_init_com") as mock_init:
            _ = client.walker
            mock_init.assert_called_once()

    def test_walker_property_skips_init_if_set(self):
        """walker property does NOT re-init if _walker is already set."""
        from windowspc_mcp.uia.core import _AutomationClient

        sentinel = object()
        with patch.object(_AutomationClient, "_init_com"):
            client = _AutomationClient()
            client._walker = sentinel

        with patch.object(_AutomationClient, "_init_com") as mock_init:
            result = client.walker
            mock_init.assert_not_called()
            assert result is sentinel


class TestGetAutomationClient:
    """get_automation_client() module-level accessor."""

    def test_returns_automation_client(self):
        from windowspc_mcp.uia.core import get_automation_client, _AutomationClient

        with patch.object(_AutomationClient, "_init_com"):
            client = get_automation_client()
            assert isinstance(client, _AutomationClient)

    def test_returns_same_singleton(self):
        from windowspc_mcp.uia.core import get_automation_client, _AutomationClient

        with patch.object(_AutomationClient, "_init_com"):
            a = get_automation_client()
            b = get_automation_client()
            assert a is b
