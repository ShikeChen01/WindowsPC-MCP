"""Smoke test markers — real system calls, no mocks."""

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "network: requires internet access")
    config.addinivalue_line("markers", "vdd: requires Parsec VDD driver installed")


def _vdd_available() -> bool:
    try:
        from windowspc_mcp.display.driver import open_device_handle, CloseHandle
        h = open_device_handle()
        CloseHandle(h)
        return True
    except Exception:
        return False


def pytest_collection_modifyitems(items):
    skip_vdd = pytest.mark.skip(reason="Parsec VDD driver not installed")
    for item in items:
        if "vdd" in item.keywords and not _vdd_available():
            item.add_marker(skip_vdd)
