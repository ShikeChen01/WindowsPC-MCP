"""Unit tests for the Parsec VDD driver wrapper."""

import pytest
from unittest.mock import patch, MagicMock
from windowspc_mcp.display.driver import (
    ParsecVDD,
    VDD_IOCTL_ADD,
    VDD_IOCTL_REMOVE,
    VDD_IOCTL_UPDATE,
    VDD_IOCTL_VERSION,
    open_device_handle,
)


class TestParseVDDConstants:
    def test_ioctl_codes(self):
        assert VDD_IOCTL_ADD == 0x0022E004
        assert VDD_IOCTL_REMOVE == 0x0022A008
        assert VDD_IOCTL_UPDATE == 0x0022A00C
        assert VDD_IOCTL_VERSION == 0x0022E010


class TestParseVDDOpenHandle:
    @patch("windowspc_mcp.display.driver.SetupDiGetClassDevsA")
    def test_raises_when_driver_not_found(self, mock_setup):
        mock_setup.return_value = -1  # INVALID_HANDLE_VALUE
        with pytest.raises(OSError, match="Could not find Parsec VDD"):
            open_device_handle()


class TestParseVDDLifecycle:
    @patch("windowspc_mcp.display.driver.open_device_handle")
    def test_context_manager_opens_and_closes(self, mock_open):
        mock_handle = MagicMock()
        mock_open.return_value = mock_handle
        with patch("windowspc_mcp.display.driver.vdd_update"):
            with patch("windowspc_mcp.display.driver.CloseHandle") as mock_close:
                vdd = ParsecVDD()
                vdd.close()
                mock_close.assert_called_once_with(mock_handle)
