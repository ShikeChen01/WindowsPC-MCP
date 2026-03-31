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
    """Verify Parsec VDD driver ctypes structures match Win32 ABI."""

    def test_guid(self):
        from windowspc_mcp.display.driver import GUID, VDD_ADAPTER_GUID
        assert ctypes.sizeof(GUID) == 16
        assert VDD_ADAPTER_GUID.Data1 == 0x00B41627

    def test_sp_device_interface_data(self):
        from windowspc_mcp.display.driver import SP_DEVICE_INTERFACE_DATA
        d = SP_DEVICE_INTERFACE_DATA()
        d.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)
        assert d.cbSize > 0

    def test_sp_device_interface_data_reserved_is_pointer_sized(self):
        """Reserved field is ULONG_PTR — must be pointer-sized, not DWORD."""
        from windowspc_mcp.display.driver import SP_DEVICE_INTERFACE_DATA
        ptr_size = ctypes.sizeof(ctypes.c_void_p)
        reserved_offset = SP_DEVICE_INTERFACE_DATA.Reserved.offset
        total_size = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)
        # Reserved is the last field; its size = total - offset
        reserved_size = total_size - reserved_offset
        assert reserved_size == ptr_size

    def test_overlapped(self):
        from windowspc_mcp.display.driver import OVERLAPPED
        o = OVERLAPPED()
        assert o.hEvent is None or o.hEvent == 0  # c_void_p defaults to None

    def test_overlapped_sizeof(self):
        """OVERLAPPED must be 32 bytes on 64-bit, 20 bytes on 32-bit."""
        from windowspc_mcp.display.driver import OVERLAPPED
        ptr_size = ctypes.sizeof(ctypes.c_void_p)
        expected = 32 if ptr_size == 8 else 20
        assert ctypes.sizeof(OVERLAPPED) == expected

    def test_overlapped_field_offsets(self):
        """Validate OVERLAPPED field offsets match Win32 ABI.

        On 64-bit: Internal(0,8) InternalHigh(8,8) Offset(16,4) OffsetHigh(20,4) hEvent(24,8)
        On 32-bit: Internal(0,4) InternalHigh(4,4) Offset(8,4)  OffsetHigh(12,4) hEvent(16,4)
        """
        from windowspc_mcp.display.driver import OVERLAPPED
        ptr_size = ctypes.sizeof(ctypes.c_void_p)

        assert OVERLAPPED.Internal.offset == 0
        assert OVERLAPPED.InternalHigh.offset == ptr_size
        assert OVERLAPPED.Offset.offset == ptr_size * 2
        assert OVERLAPPED.OffsetHigh.offset == ptr_size * 2 + 4
        expected_hevent = 24 if ptr_size == 8 else 16
        assert OVERLAPPED.hEvent.offset == expected_hevent
