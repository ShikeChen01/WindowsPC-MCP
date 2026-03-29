"""Production-grade tests for windowspc_mcp.display.driver.

All Win32 API calls (ctypes, setupapi, kernel32) are mocked at the boundary.
"""

import ctypes
import struct
import threading
import pytest
from unittest.mock import patch, MagicMock, call


# =========================================================================
# open_device_handle
# =========================================================================


class TestOpenDeviceHandle:
    """Tests for open_device_handle: all early-exit and success paths."""

    @patch("windowspc_mcp.display.driver.SetupDiDestroyDeviceInfoList")
    @patch("windowspc_mcp.display.driver.SetupDiGetClassDevsA")
    def test_invalid_handle_value_raises(self, mock_get_devs, mock_destroy):
        from windowspc_mcp.display.driver import INVALID_HANDLE_VALUE
        mock_get_devs.return_value = INVALID_HANDLE_VALUE
        with pytest.raises(OSError, match="Could not find Parsec VDD device info set"):
            from windowspc_mcp.display.driver import open_device_handle
            open_device_handle()

    @patch("windowspc_mcp.display.driver.SetupDiDestroyDeviceInfoList")
    @patch("windowspc_mcp.display.driver.SetupDiGetClassDevsA")
    def test_none_handle_raises(self, mock_get_devs, mock_destroy):
        mock_get_devs.return_value = None
        with pytest.raises(OSError, match="Could not find Parsec VDD device info set"):
            from windowspc_mcp.display.driver import open_device_handle
            open_device_handle()

    @patch("windowspc_mcp.display.driver.SetupDiDestroyDeviceInfoList")
    @patch("windowspc_mcp.display.driver.SetupDiGetClassDevsA")
    def test_zero_handle_raises(self, mock_get_devs, mock_destroy):
        mock_get_devs.return_value = 0
        with pytest.raises(OSError, match="Could not find Parsec VDD device info set"):
            from windowspc_mcp.display.driver import open_device_handle
            open_device_handle()

    @patch("windowspc_mcp.display.driver.SetupDiDestroyDeviceInfoList")
    @patch("windowspc_mcp.display.driver.SetupDiEnumDeviceInterfaces")
    @patch("windowspc_mcp.display.driver.SetupDiGetClassDevsA")
    def test_interface_not_found_raises(self, mock_get_devs, mock_enum_iface, mock_destroy):
        mock_get_devs.return_value = 42  # valid handle
        mock_enum_iface.return_value = False
        with pytest.raises(OSError, match="Could not find Parsec VDD device interface"):
            from windowspc_mcp.display.driver import open_device_handle
            open_device_handle()
        mock_destroy.assert_called_once_with(42)

    @patch("windowspc_mcp.display.driver.SetupDiDestroyDeviceInfoList")
    @patch("windowspc_mcp.display.driver.CreateFileA")
    @patch("windowspc_mcp.display.driver.SetupDiGetDeviceInterfaceDetailA")
    @patch("windowspc_mcp.display.driver.SetupDiEnumDeviceInterfaces")
    @patch("windowspc_mcp.display.driver.SetupDiGetClassDevsA")
    @patch("windowspc_mcp.display.driver.byref", side_effect=lambda x: x)
    @patch("windowspc_mcp.display.driver.sizeof", return_value=28)
    def test_empty_device_path_raises(
        self, mock_sizeof, mock_byref, mock_get_devs, mock_enum_iface, mock_detail, mock_create, mock_destroy
    ):
        mock_get_devs.return_value = 42
        mock_enum_iface.return_value = True

        with patch("windowspc_mcp.display.driver.SP_DEVICE_INTERFACE_DETAIL_DATA_A") as MockDetail:
            instance = MagicMock()
            instance.DevicePath = b""
            MockDetail.return_value = instance
            with patch("windowspc_mcp.display.driver.SP_DEVICE_INTERFACE_DATA") as MockIfaceData:
                iface_inst = MagicMock()
                MockIfaceData.return_value = iface_inst
                with pytest.raises(OSError, match="Could not find Parsec VDD"):
                    from windowspc_mcp.display.driver import open_device_handle
                    open_device_handle()
        mock_destroy.assert_called_with(42)

    @patch("windowspc_mcp.display.driver.SetupDiDestroyDeviceInfoList")
    @patch("windowspc_mcp.display.driver.CreateFileA")
    @patch("windowspc_mcp.display.driver.SetupDiGetDeviceInterfaceDetailA")
    @patch("windowspc_mcp.display.driver.SetupDiEnumDeviceInterfaces")
    @patch("windowspc_mcp.display.driver.SetupDiGetClassDevsA")
    @patch("windowspc_mcp.display.driver.byref", side_effect=lambda x: x)
    @patch("windowspc_mcp.display.driver.sizeof", return_value=28)
    def test_invalid_file_handle_raises(
        self, mock_sizeof, mock_byref, mock_get_devs, mock_enum_iface, mock_detail, mock_create, mock_destroy
    ):
        from windowspc_mcp.display.driver import INVALID_HANDLE_VALUE
        mock_get_devs.return_value = 42
        mock_enum_iface.return_value = True
        mock_create.return_value = INVALID_HANDLE_VALUE

        with patch("windowspc_mcp.display.driver.SP_DEVICE_INTERFACE_DETAIL_DATA_A") as MockDetail:
            instance = MagicMock()
            instance.DevicePath = b"\\\\?\\valid_path"
            MockDetail.return_value = instance
            with patch("windowspc_mcp.display.driver.SP_DEVICE_INTERFACE_DATA") as MockIfaceData:
                iface_inst = MagicMock()
                MockIfaceData.return_value = iface_inst
                with pytest.raises(OSError, match="Could not find Parsec VDD"):
                    from windowspc_mcp.display.driver import open_device_handle
                    open_device_handle()
        mock_destroy.assert_called_with(42)

    @patch("windowspc_mcp.display.driver.SetupDiDestroyDeviceInfoList")
    @patch("windowspc_mcp.display.driver.CreateFileA")
    @patch("windowspc_mcp.display.driver.SetupDiGetDeviceInterfaceDetailA")
    @patch("windowspc_mcp.display.driver.SetupDiEnumDeviceInterfaces")
    @patch("windowspc_mcp.display.driver.SetupDiGetClassDevsA")
    @patch("windowspc_mcp.display.driver.byref", side_effect=lambda x: x)
    @patch("windowspc_mcp.display.driver.sizeof", return_value=28)
    def test_success_returns_handle(
        self, mock_sizeof, mock_byref, mock_get_devs, mock_enum_iface, mock_detail, mock_create, mock_destroy
    ):
        mock_get_devs.return_value = 42
        mock_enum_iface.return_value = True
        mock_create.return_value = 99  # valid handle

        with patch("windowspc_mcp.display.driver.SP_DEVICE_INTERFACE_DETAIL_DATA_A") as MockDetail:
            instance = MagicMock()
            instance.DevicePath = b"\\\\?\\valid_path"
            MockDetail.return_value = instance
            with patch("windowspc_mcp.display.driver.SP_DEVICE_INTERFACE_DATA") as MockIfaceData:
                iface_inst = MagicMock()
                MockIfaceData.return_value = iface_inst
                from windowspc_mcp.display.driver import open_device_handle
                handle = open_device_handle()
                assert handle == 99
        mock_destroy.assert_called_with(42)


# =========================================================================
# _vdd_ioctl
# =========================================================================


class TestVddIoctl:
    """Tests for _vdd_ioctl: event failure, IO pending, timeout, general failure, success."""

    @patch("windowspc_mcp.display.driver.CreateEventA", return_value=None)
    def test_event_creation_failure(self, mock_event):
        from windowspc_mcp.display.driver import _vdd_ioctl
        with pytest.raises(OSError, match="CreateEventA failed"):
            _vdd_ioctl(42, 0x0022E004, b"\x00\x00\x00\x00", 4)

    @patch("windowspc_mcp.display.driver.CreateEventA", return_value=0)
    def test_event_creation_failure_zero(self, mock_event):
        from windowspc_mcp.display.driver import _vdd_ioctl
        with pytest.raises(OSError, match="CreateEventA failed"):
            _vdd_ioctl(42, 0x0022E004, b"\x00\x00\x00\x00", 4)

    @patch("windowspc_mcp.display.driver.CloseHandle")
    @patch("windowspc_mcp.display.driver.GetOverlappedResultEx")
    @patch("windowspc_mcp.display.driver.ctypes.get_last_error")
    @patch("windowspc_mcp.display.driver.DeviceIoControl", return_value=True)
    @patch("windowspc_mcp.display.driver.CreateEventA", return_value=100)
    def test_success_immediate(self, mock_event, mock_ioctl, mock_err, mock_result, mock_close):
        """DeviceIoControl returns True immediately (no IO_PENDING)."""
        from windowspc_mcp.display.driver import _vdd_ioctl

        mock_result.return_value = True
        result = _vdd_ioctl(42, 0x0022E004, b"\x00\x00\x00\x00", 4)
        assert isinstance(result, int)
        mock_close.assert_called_once_with(100)

    @patch("windowspc_mcp.display.driver.CloseHandle")
    @patch("windowspc_mcp.display.driver.GetOverlappedResultEx")
    @patch("windowspc_mcp.display.driver.ctypes.get_last_error")
    @patch("windowspc_mcp.display.driver.DeviceIoControl", return_value=False)
    @patch("windowspc_mcp.display.driver.CreateEventA", return_value=100)
    def test_io_pending_then_success(self, mock_event, mock_ioctl, mock_err, mock_result, mock_close):
        """DeviceIoControl returns False with ERROR_IO_PENDING, then GetOverlappedResult succeeds."""
        from windowspc_mcp.display.driver import _vdd_ioctl, ERROR_IO_PENDING

        mock_err.return_value = ERROR_IO_PENDING
        mock_result.return_value = True

        result = _vdd_ioctl(42, 0x0022E004, b"\x00\x00\x00\x00", 4)
        assert isinstance(result, int)
        mock_close.assert_called_once_with(100)

    @patch("windowspc_mcp.display.driver.CloseHandle")
    @patch("windowspc_mcp.display.driver.ctypes.get_last_error")
    @patch("windowspc_mcp.display.driver.DeviceIoControl", return_value=False)
    @patch("windowspc_mcp.display.driver.CreateEventA", return_value=100)
    def test_general_failure(self, mock_event, mock_ioctl, mock_err, mock_close):
        """DeviceIoControl returns False with a non-IO_PENDING error."""
        from windowspc_mcp.display.driver import _vdd_ioctl

        mock_err.return_value = 5  # ACCESS_DENIED
        with pytest.raises(OSError, match="DeviceIoControl failed with error 5"):
            _vdd_ioctl(42, 0x0022E004, b"\x00\x00\x00\x00", 4)
        mock_close.assert_called_once_with(100)

    @patch("windowspc_mcp.display.driver.CloseHandle")
    @patch("windowspc_mcp.display.driver.GetOverlappedResultEx")
    @patch("windowspc_mcp.display.driver.ctypes.get_last_error")
    @patch("windowspc_mcp.display.driver.DeviceIoControl", return_value=True)
    @patch("windowspc_mcp.display.driver.CreateEventA", return_value=100)
    def test_timeout(self, mock_event, mock_ioctl, mock_err_ioctl, mock_result, mock_close):
        """GetOverlappedResultEx fails with WAIT_TIMEOUT."""
        from windowspc_mcp.display.driver import _vdd_ioctl, WAIT_TIMEOUT

        mock_result.return_value = False
        # get_last_error called twice: once after DeviceIoControl (ok=True so branch skipped),
        # once after GetOverlappedResultEx
        mock_err_ioctl.side_effect = [0, WAIT_TIMEOUT]

        with pytest.raises(OSError, match="timed out"):
            _vdd_ioctl(42, 0x0022E004, b"\x00\x00\x00\x00", 4)
        mock_close.assert_called_once_with(100)

    @patch("windowspc_mcp.display.driver.CloseHandle")
    @patch("windowspc_mcp.display.driver.GetOverlappedResultEx")
    @patch("windowspc_mcp.display.driver.ctypes.get_last_error")
    @patch("windowspc_mcp.display.driver.DeviceIoControl", return_value=True)
    @patch("windowspc_mcp.display.driver.CreateEventA", return_value=100)
    def test_overlapped_result_general_failure(
        self, mock_event, mock_ioctl, mock_err, mock_result, mock_close
    ):
        """GetOverlappedResultEx fails with a non-timeout error."""
        from windowspc_mcp.display.driver import _vdd_ioctl

        mock_result.return_value = False
        mock_err.side_effect = [0, 6]  # ERROR_INVALID_HANDLE

        with pytest.raises(OSError, match="GetOverlappedResultEx failed with error 6"):
            _vdd_ioctl(42, 0x0022E004, b"\x00\x00\x00\x00", 4)
        mock_close.assert_called_once_with(100)


# =========================================================================
# vdd_add_display / vdd_remove_display / vdd_update / vdd_version
# =========================================================================


class TestVddAddDisplay:
    """Tests for vdd_add_display."""

    @patch("windowspc_mcp.display.driver.vdd_update")
    @patch("windowspc_mcp.display.driver._vdd_ioctl")
    def test_returns_index(self, mock_ioctl, mock_update):
        from windowspc_mcp.display.driver import vdd_add_display, VDD_IOCTL_ADD

        def side_effect(handle, code, data, size):
            # Simulate driver writing index 3 into first byte
            data[0] = b'\x03'
            return 4

        mock_ioctl.side_effect = side_effect
        index = vdd_add_display(42)
        # buf[0] is b'\x03'
        assert index == b'\x03'
        mock_update.assert_called_once_with(42)


class TestVddRemoveDisplay:
    """Tests for vdd_remove_display."""

    @patch("windowspc_mcp.display.driver._vdd_ioctl")
    def test_sends_correct_ioctl(self, mock_ioctl):
        from windowspc_mcp.display.driver import vdd_remove_display, VDD_IOCTL_REMOVE

        vdd_remove_display(42, 5)
        mock_ioctl.assert_called_once()
        args = mock_ioctl.call_args
        assert args[0][0] == 42
        assert args[0][1] == VDD_IOCTL_REMOVE
        assert args[0][3] == 2


class TestVddUpdate:
    """Tests for vdd_update."""

    @patch("windowspc_mcp.display.driver._vdd_ioctl")
    def test_sends_update_ioctl(self, mock_ioctl):
        from windowspc_mcp.display.driver import vdd_update, VDD_IOCTL_UPDATE

        vdd_update(42)
        mock_ioctl.assert_called_once()
        assert mock_ioctl.call_args[0][1] == VDD_IOCTL_UPDATE


class TestVddVersion:
    """Tests for vdd_version."""

    @patch("windowspc_mcp.display.driver._vdd_ioctl")
    def test_returns_version_int(self, mock_ioctl):
        from windowspc_mcp.display.driver import vdd_version, VDD_IOCTL_VERSION

        def side_effect(handle, code, data, size):
            # Write version 0x00010002 as little-endian into buffer
            data[0] = b'\x02'
            data[1] = b'\x00'
            data[2] = b'\x01'
            data[3] = b'\x00'
            return 4

        mock_ioctl.side_effect = side_effect
        version = vdd_version(42)
        assert version == 0x00010002


# =========================================================================
# ParsecVDD class
# =========================================================================


class TestParsecVDDInit:
    """ParsecVDD.__init__: opens handle, starts keepalive thread."""

    @patch("windowspc_mcp.display.driver.vdd_update")
    @patch("windowspc_mcp.display.driver.open_device_handle", return_value=99)
    def test_init_opens_handle_and_starts_thread(self, mock_open, mock_update):
        from windowspc_mcp.display.driver import ParsecVDD, CloseHandle

        vdd = ParsecVDD()
        assert vdd._handle == 99
        assert vdd._thread.is_alive()
        assert vdd._displays == []

        vdd._stop_event.set()
        vdd._thread.join(timeout=1.0)
        CloseHandle(99)


class TestParsecVDDAddDisplay:
    """ParsecVDD.add_display: thread-safe, appends to displays list."""

    @patch("windowspc_mcp.display.driver.vdd_update")
    @patch("windowspc_mcp.display.driver.vdd_add_display", return_value=3)
    @patch("windowspc_mcp.display.driver.open_device_handle", return_value=99)
    def test_add_display(self, mock_open, mock_add, mock_update):
        from windowspc_mcp.display.driver import ParsecVDD, CloseHandle

        vdd = ParsecVDD()
        idx = vdd.add_display()
        assert idx == 3
        assert 3 in vdd._displays

        vdd._stop_event.set()
        vdd._thread.join(timeout=1.0)
        CloseHandle(99)


class TestParsecVDDRemoveDisplay:
    """ParsecVDD.remove_display: removes from list, handles ValueError."""

    @patch("windowspc_mcp.display.driver.vdd_update")
    @patch("windowspc_mcp.display.driver.vdd_remove_display")
    @patch("windowspc_mcp.display.driver.open_device_handle", return_value=99)
    def test_remove_display(self, mock_open, mock_remove, mock_update):
        from windowspc_mcp.display.driver import ParsecVDD, CloseHandle

        vdd = ParsecVDD()
        vdd._displays = [1, 2, 3]
        vdd.remove_display(2)
        assert 2 not in vdd._displays
        mock_remove.assert_called_once_with(99, 2)

        vdd._stop_event.set()
        vdd._thread.join(timeout=1.0)
        CloseHandle(99)

    @patch("windowspc_mcp.display.driver.vdd_update")
    @patch("windowspc_mcp.display.driver.vdd_remove_display")
    @patch("windowspc_mcp.display.driver.open_device_handle", return_value=99)
    def test_remove_display_not_in_list(self, mock_open, mock_remove, mock_update):
        """Removing a display index that's not in _displays doesn't raise."""
        from windowspc_mcp.display.driver import ParsecVDD, CloseHandle

        vdd = ParsecVDD()
        vdd._displays = [1, 3]
        vdd.remove_display(42)  # not in list
        mock_remove.assert_called_once_with(99, 42)
        assert vdd._displays == [1, 3]

        vdd._stop_event.set()
        vdd._thread.join(timeout=1.0)
        CloseHandle(99)


class TestParsecVDDRemoveAll:
    """ParsecVDD.remove_all: removes all, errors suppressed."""

    @patch("windowspc_mcp.display.driver.vdd_update")
    @patch("windowspc_mcp.display.driver.vdd_remove_display")
    @patch("windowspc_mcp.display.driver.open_device_handle", return_value=99)
    def test_remove_all(self, mock_open, mock_remove, mock_update):
        from windowspc_mcp.display.driver import ParsecVDD, CloseHandle

        vdd = ParsecVDD()
        vdd._displays = [0, 1, 2]
        vdd.remove_all()
        assert vdd._displays == []
        assert mock_remove.call_count == 3

        vdd._stop_event.set()
        vdd._thread.join(timeout=1.0)
        CloseHandle(99)

    @patch("windowspc_mcp.display.driver.vdd_update")
    @patch("windowspc_mcp.display.driver.vdd_remove_display")
    @patch("windowspc_mcp.display.driver.open_device_handle", return_value=99)
    def test_remove_all_with_errors(self, mock_open, mock_remove, mock_update):
        """remove_all suppresses OSError for individual removals."""
        from windowspc_mcp.display.driver import ParsecVDD, CloseHandle

        mock_remove.side_effect = [None, OSError("fail"), None]
        vdd = ParsecVDD()
        vdd._displays = [0, 1, 2]
        vdd.remove_all()  # should not raise
        assert vdd._displays == []

        vdd._stop_event.set()
        vdd._thread.join(timeout=1.0)
        CloseHandle(99)


class TestParsecVDDVersion:
    """ParsecVDD.version: delegates to vdd_version."""

    @patch("windowspc_mcp.display.driver.vdd_update")
    @patch("windowspc_mcp.display.driver.vdd_version", return_value=42)
    @patch("windowspc_mcp.display.driver.open_device_handle", return_value=99)
    def test_version(self, mock_open, mock_ver, mock_update):
        from windowspc_mcp.display.driver import ParsecVDD, CloseHandle

        vdd = ParsecVDD()
        assert vdd.version() == 42
        mock_ver.assert_called_once_with(99)

        vdd._stop_event.set()
        vdd._thread.join(timeout=1.0)
        CloseHandle(99)


class TestParsecVDDActiveDisplays:
    """ParsecVDD.active_displays: returns a copy."""

    @patch("windowspc_mcp.display.driver.vdd_update")
    @patch("windowspc_mcp.display.driver.open_device_handle", return_value=99)
    def test_active_displays_is_copy(self, mock_open, mock_update):
        from windowspc_mcp.display.driver import ParsecVDD, CloseHandle

        vdd = ParsecVDD()
        vdd._displays = [1, 2, 3]
        result = vdd.active_displays
        assert result == [1, 2, 3]
        assert result is not vdd._displays

        vdd._stop_event.set()
        vdd._thread.join(timeout=1.0)
        CloseHandle(99)


class TestParsecVDDClose:
    """ParsecVDD.close: stops thread, removes all, closes handle."""

    @patch("windowspc_mcp.display.driver.CloseHandle")
    @patch("windowspc_mcp.display.driver.vdd_update")
    @patch("windowspc_mcp.display.driver.vdd_remove_display")
    @patch("windowspc_mcp.display.driver.open_device_handle", return_value=99)
    def test_close(self, mock_open, mock_remove, mock_update, mock_close):
        from windowspc_mcp.display.driver import ParsecVDD

        vdd = ParsecVDD()
        vdd._displays = [0, 1]
        vdd.close()

        assert vdd._stop_event.is_set()
        assert not vdd._thread.is_alive()
        mock_close.assert_called_once_with(99)

    @patch("windowspc_mcp.display.driver.CloseHandle")
    @patch("windowspc_mcp.display.driver.vdd_update")
    @patch("windowspc_mcp.display.driver.open_device_handle", return_value=99)
    def test_close_remove_all_oserror_suppressed(self, mock_open, mock_update, mock_close):
        """close() suppresses OSError from remove_all."""
        from windowspc_mcp.display.driver import ParsecVDD

        vdd = ParsecVDD()
        with patch.object(vdd, "remove_all", side_effect=OSError("fail")):
            vdd.close()  # should not raise
        mock_close.assert_called_once_with(99)


class TestParsecVDDContextManager:
    """ParsecVDD.__enter__ / __exit__."""

    @patch("windowspc_mcp.display.driver.CloseHandle")
    @patch("windowspc_mcp.display.driver.vdd_update")
    @patch("windowspc_mcp.display.driver.open_device_handle", return_value=99)
    def test_enter_returns_self(self, mock_open, mock_update, mock_close):
        from windowspc_mcp.display.driver import ParsecVDD

        vdd = ParsecVDD()
        assert vdd.__enter__() is vdd
        vdd.close()

    @patch("windowspc_mcp.display.driver.CloseHandle")
    @patch("windowspc_mcp.display.driver.vdd_update")
    @patch("windowspc_mcp.display.driver.open_device_handle", return_value=99)
    def test_exit_calls_close(self, mock_open, mock_update, mock_close):
        from windowspc_mcp.display.driver import ParsecVDD

        vdd = ParsecVDD()
        with patch.object(vdd, "close") as mock_close_method:
            vdd.__exit__(None, None, None)
            mock_close_method.assert_called_once()

    @patch("windowspc_mcp.display.driver.CloseHandle")
    @patch("windowspc_mcp.display.driver.vdd_update")
    @patch("windowspc_mcp.display.driver.open_device_handle", return_value=99)
    def test_context_manager_protocol(self, mock_open, mock_update, mock_close):
        from windowspc_mcp.display.driver import ParsecVDD

        with ParsecVDD() as vdd:
            assert isinstance(vdd, ParsecVDD)
        # After exiting, the close should have been called
        mock_close.assert_called()


class TestParsecVDDKeepalive:
    """ParsecVDD keepalive thread behavior."""

    @patch("windowspc_mcp.display.driver.CloseHandle")
    @patch("windowspc_mcp.display.driver.vdd_update")
    @patch("windowspc_mcp.display.driver.open_device_handle", return_value=99)
    def test_keepalive_calls_update(self, mock_open, mock_update, mock_close):
        from windowspc_mcp.display.driver import ParsecVDD
        import time

        vdd = ParsecVDD()
        # Let it run a bit
        time.sleep(0.15)
        vdd.close()
        # Should have called vdd_update at least once from the keepalive thread
        assert mock_update.call_count >= 1

    @patch("windowspc_mcp.display.driver.CloseHandle")
    @patch("windowspc_mcp.display.driver.vdd_update")
    @patch("windowspc_mcp.display.driver.open_device_handle", return_value=99)
    def test_keepalive_suppresses_oserror(self, mock_open, mock_update, mock_close):
        """OSError in keepalive thread is silently ignored."""
        from windowspc_mcp.display.driver import ParsecVDD
        import time

        mock_update.side_effect = OSError("transient")
        vdd = ParsecVDD()
        time.sleep(0.15)
        # Thread should still be alive (errors suppressed)
        assert vdd._thread.is_alive()
        vdd._stop_event.set()
        vdd._thread.join(timeout=1.0)
