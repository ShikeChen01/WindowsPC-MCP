"""Smoke: real driver detection — no mocks.

Tests that work regardless of whether VDD is installed.
"""

import pytest


class TestDriverDetection:
    """check_driver() must return a bool without crashing."""

    def test_check_driver_returns_bool(self):
        from windowspc_mcp.display.manager import DisplayManager
        dm = DisplayManager()
        result = dm.check_driver()
        assert isinstance(result, bool)

    def test_check_driver_is_idempotent(self):
        from windowspc_mcp.display.manager import DisplayManager
        dm = DisplayManager()
        r1 = dm.check_driver()
        r2 = dm.check_driver()
        assert r1 == r2


class TestOpenDeviceHandle:
    """open_device_handle must either succeed or raise OSError."""

    def test_does_not_crash(self):
        from windowspc_mcp.display.driver import open_device_handle, CloseHandle
        try:
            handle = open_device_handle()
            CloseHandle(handle)
        except OSError:
            pass  # expected if VDD not installed


@pytest.mark.vdd
class TestDriverWithVDD:
    """Tests that only run when VDD driver is installed."""

    def test_open_handle_succeeds(self):
        from windowspc_mcp.display.driver import open_device_handle, CloseHandle
        handle = open_device_handle()
        assert handle is not None
        CloseHandle(handle)

    def test_parsec_vdd_lifecycle(self):
        from windowspc_mcp.display.driver import ParsecVDD
        with ParsecVDD() as vdd:
            ver = vdd.version()
            assert isinstance(ver, int)
            assert ver > 0
