"""Smoke: verify all ctypes structures instantiate on this Python version.

No mocks — these catch missing attributes like ctypes.wintypes.WNDCLASS.
"""

import ctypes
import ctypes.wintypes
import sys


class TestWNDCLASS:
    """The struct that broke on Python 3.13+."""

    def test_instantiate(self):
        from windowspc_mcp.confinement.bounds import WNDCLASS
        wc = WNDCLASS()
        assert wc.style == 0

    def test_assign_hinstance(self):
        from windowspc_mcp.confinement.bounds import WNDCLASS
        wc = WNDCLASS()
        hmod = ctypes.windll.kernel32.GetModuleHandleW(None)
        wc.hInstance = hmod or 0
        assert wc.hInstance != 0 or hmod == 0

    def test_assign_classname(self):
        from windowspc_mcp.confinement.bounds import WNDCLASS
        wc = WNDCLASS()
        wc.lpszClassName = "TestClass"
        assert wc.lpszClassName == "TestClass"

    def test_assign_wndproc(self):
        from windowspc_mcp.confinement.bounds import WNDCLASS, WNDPROC
        cb = WNDPROC(lambda hwnd, msg, wp, lp: 0)
        wc = WNDCLASS()
        wc.lpfnWndProc = ctypes.cast(cb, ctypes.c_void_p)
        assert wc.lpfnWndProc != 0

    def test_sizeof_matches_platform(self):
        from windowspc_mcp.confinement.bounds import WNDCLASS
        size = ctypes.sizeof(WNDCLASS)
        if sys.maxsize > 2**32:
            assert size == 72  # 64-bit
        else:
            assert size == 40  # 32-bit


class TestINPUTStructs:
    """Verify INPUT/MOUSEINPUT/KEYBDINPUT from uia.core."""

    def test_mouseinput(self):
        from windowspc_mcp.uia.core import MOUSEINPUT
        m = MOUSEINPUT()
        m.dx = 100
        m.dy = 200
        assert m.dx == 100

    def test_keybdinput(self):
        from windowspc_mcp.uia.core import KEYBDINPUT
        k = KEYBDINPUT()
        k.wVk = 0x41  # 'A'
        assert k.wVk == 0x41

    def test_input_struct(self):
        from windowspc_mcp.uia.core import INPUT, INPUT_MOUSE
        inp = INPUT()
        inp.type = INPUT_MOUSE
        assert inp.type == INPUT_MOUSE


class TestDriverStructs:
    """Verify Parsec VDD driver ctypes structures."""

    def test_guid(self):
        from windowspc_mcp.display.driver import GUID, VDD_ADAPTER_GUID
        assert ctypes.sizeof(GUID) == 16
        assert VDD_ADAPTER_GUID.Data1 == 0x00B41627

    def test_sp_device_interface_data(self):
        from windowspc_mcp.display.driver import SP_DEVICE_INTERFACE_DATA
        d = SP_DEVICE_INTERFACE_DATA()
        d.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)
        assert d.cbSize > 0

    def test_overlapped(self):
        from windowspc_mcp.display.driver import OVERLAPPED
        o = OVERLAPPED()
        assert o.hEvent is None or o.hEvent == 0  # c_void_p defaults to None
