"""Tests for windowspc_mcp.display.setup — VDD auto-download and install."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from windowspc_mcp.display.setup import (
    _find_setup_exe_url,
    _download_setup,
    _install_driver,
    ensure_driver_installed,
    _VDD_DIR,
)


# ── helpers ─────────────────────────────────────────────────────────────


def _github_payload(*asset_names: str) -> bytes:
    assets = [
        {"name": name, "browser_download_url": f"https://example.com/{name}"}
        for name in asset_names
    ]
    return json.dumps({"assets": assets}).encode()


def _mock_urlopen(payload: bytes) -> MagicMock:
    resp = MagicMock()
    resp.read.return_value = payload
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# =========================================================================
# _find_setup_exe_url
# =========================================================================


class TestFindSetupExeUrl:
    @patch("windowspc_mcp.display.setup.urllib.request.urlopen")
    def test_found(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen(
            _github_payload("ParsecVDisplay-v0.45-setup.exe", "other.zip")
        )
        url = _find_setup_exe_url()
        assert url == "https://example.com/ParsecVDisplay-v0.45-setup.exe"

    @patch("windowspc_mcp.display.setup.urllib.request.urlopen")
    def test_not_found(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen(
            _github_payload("readme.md", "checksums.txt")
        )
        with pytest.raises(RuntimeError, match="Could not find setup EXE"):
            _find_setup_exe_url()

    @patch("windowspc_mcp.display.setup.urllib.request.urlopen")
    def test_empty_assets(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen(json.dumps({"assets": []}).encode())
        with pytest.raises(RuntimeError, match="Could not find setup EXE"):
            _find_setup_exe_url()

    @patch("windowspc_mcp.display.setup.urllib.request.urlopen")
    def test_no_assets_key(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen(json.dumps({}).encode())
        with pytest.raises(RuntimeError, match="Could not find setup EXE"):
            _find_setup_exe_url()


# =========================================================================
# _download_setup
# =========================================================================


class TestDownloadSetup:
    @patch("windowspc_mcp.display.setup.urllib.request.urlretrieve")
    @patch.object(Path, "mkdir")
    @patch.object(Path, "stat")
    def test_success(self, mock_stat, mock_mkdir, mock_retrieve):
        mock_stat.return_value = MagicMock(st_size=2048000)
        result = _download_setup("https://example.com/ParsecVDisplay-v0.45-setup.exe")
        assert result == _VDD_DIR / "ParsecVDisplay-v0.45-setup.exe"
        mock_retrieve.assert_called_once()
        mock_mkdir.assert_called()

    @patch("windowspc_mcp.display.setup.urllib.request.urlretrieve", side_effect=OSError("net"))
    @patch.object(Path, "mkdir")
    def test_download_failure_propagates(self, mock_mkdir, mock_retrieve):
        with pytest.raises(OSError, match="net"):
            _download_setup("https://example.com/setup.exe")


# =========================================================================
# _install_driver
# =========================================================================


class TestInstallDriver:
    @patch("time.sleep")
    @patch("ctypes.windll")
    def test_success(self, mock_windll, mock_sleep):
        mock_windll.shell32.ShellExecuteW.return_value = 42
        setup = Path("C:/vdd/setup.exe")
        _install_driver(setup)
        mock_windll.shell32.ShellExecuteW.assert_called_once()
        call_args = mock_windll.shell32.ShellExecuteW.call_args[0]
        assert call_args[1] == "runas"
        assert call_args[2] == str(setup)
        assert "/VERYSILENT" in call_args[3]
        assert "/NORESTART" in call_args[3]
        mock_sleep.assert_called_once_with(10)

    @patch("ctypes.windll")
    def test_failure_raises(self, mock_windll):
        mock_windll.shell32.ShellExecuteW.return_value = 5
        with pytest.raises(RuntimeError, match="VDD installer failed"):
            _install_driver(Path("C:/vdd/setup.exe"))

    @patch("time.sleep")
    @patch("ctypes.windll")
    def test_working_dir_is_parent(self, mock_windll, mock_sleep):
        mock_windll.shell32.ShellExecuteW.return_value = 42
        setup = Path("C:/some/path/setup.exe")
        _install_driver(setup)
        call_args = mock_windll.shell32.ShellExecuteW.call_args[0]
        assert call_args[4] == str(setup.parent)


# =========================================================================
# ensure_driver_installed
# =========================================================================


class TestEnsureDriverInstalled:
    @patch("windowspc_mcp.display.driver.CloseHandle")
    @patch("windowspc_mcp.display.driver.open_device_handle")
    def test_already_present(self, mock_open, mock_close):
        mock_open.return_value = MagicMock()
        assert ensure_driver_installed() is True
        mock_open.assert_called_once()
        mock_close.assert_called_once()

    @patch("windowspc_mcp.display.setup._install_driver")
    @patch("windowspc_mcp.display.setup._download_setup")
    @patch("windowspc_mcp.display.setup._find_setup_exe_url")
    @patch("windowspc_mcp.display.driver.CloseHandle")
    @patch("windowspc_mcp.display.driver.open_device_handle")
    def test_install_and_verify_success(self, mock_open, mock_close, mock_url, mock_dl, mock_inst):
        handle = MagicMock()
        mock_open.side_effect = [OSError("no"), handle]
        mock_url.return_value = "https://example.com/setup.exe"
        mock_dl.return_value = Path("C:/vdd/setup.exe")
        assert ensure_driver_installed() is True
        mock_inst.assert_called_once()
        assert mock_open.call_count == 2

    @patch("windowspc_mcp.display.setup._find_setup_exe_url")
    @patch("windowspc_mcp.display.driver.CloseHandle")
    @patch("windowspc_mcp.display.driver.open_device_handle")
    def test_install_fails(self, mock_open, mock_close, mock_url):
        mock_open.side_effect = OSError("no")
        mock_url.side_effect = RuntimeError("no exe")
        assert ensure_driver_installed() is False

    @patch("windowspc_mcp.display.setup._install_driver")
    @patch("windowspc_mcp.display.setup._download_setup")
    @patch("windowspc_mcp.display.setup._find_setup_exe_url")
    @patch("windowspc_mcp.display.driver.CloseHandle")
    @patch("windowspc_mcp.display.driver.open_device_handle")
    def test_verify_fails(self, mock_open, mock_close, mock_url, mock_dl, mock_inst):
        mock_open.side_effect = [OSError("no"), OSError("still no")]
        mock_url.return_value = "https://example.com/setup.exe"
        mock_dl.return_value = Path("C:/vdd/setup.exe")
        assert ensure_driver_installed() is False
        assert mock_open.call_count == 2

    @patch("windowspc_mcp.display.setup._download_setup")
    @patch("windowspc_mcp.display.setup._find_setup_exe_url")
    @patch("windowspc_mcp.display.driver.CloseHandle")
    @patch("windowspc_mcp.display.driver.open_device_handle")
    def test_download_fails(self, mock_open, mock_close, mock_url, mock_dl):
        mock_open.side_effect = OSError("no")
        mock_url.return_value = "https://example.com/setup.exe"
        mock_dl.side_effect = OSError("network fail")
        assert ensure_driver_installed() is False
