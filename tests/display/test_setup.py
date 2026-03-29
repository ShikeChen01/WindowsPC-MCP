"""Production-grade tests for windowspc_mcp.display.setup.

Network, file-system, and shell operations are fully mocked.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from windowspc_mcp.display.setup import (
    _find_portable_zip_url,
    _download_and_extract,
    _find_nefconw,
    _find_inf,
    _install_driver,
    ensure_driver_installed,
    _VDD_DIR,
    _HARDWARE_ID,
    _DISPLAY_CLASS_GUID,
)


# ── helpers ─────────────────────────────────────────────────────────────


def _github_payload(*asset_names: str) -> bytes:
    """Build a minimal GitHub releases JSON payload."""
    assets = [
        {"name": name, "browser_download_url": f"https://example.com/{name}"}
        for name in asset_names
    ]
    return json.dumps({"assets": assets}).encode()


def _mock_urlopen(payload: bytes) -> MagicMock:
    """Mock context-manager response for urlopen."""
    resp = MagicMock()
    resp.read.return_value = payload
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# =========================================================================
# _find_portable_zip_url
# =========================================================================


class TestFindPortableZipUrl:
    """All branches: found, not found, empty assets, no assets key."""

    @patch("windowspc_mcp.display.setup.urllib.request.urlopen")
    def test_found(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen(
            _github_payload("driver.exe", "driver-0.45-portable.zip", "checksums.txt")
        )
        url = _find_portable_zip_url()
        assert url == "https://example.com/driver-0.45-portable.zip"

    @patch("windowspc_mcp.display.setup.urllib.request.urlopen")
    def test_not_found(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen(
            _github_payload("driver.exe", "checksums.txt")
        )
        with pytest.raises(RuntimeError, match="Could not find portable ZIP"):
            _find_portable_zip_url()

    @patch("windowspc_mcp.display.setup.urllib.request.urlopen")
    def test_empty_assets(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen(json.dumps({"assets": []}).encode())
        with pytest.raises(RuntimeError, match="Could not find portable ZIP"):
            _find_portable_zip_url()

    @patch("windowspc_mcp.display.setup.urllib.request.urlopen")
    def test_no_assets_key(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen(json.dumps({}).encode())
        with pytest.raises(RuntimeError, match="Could not find portable ZIP"):
            _find_portable_zip_url()

    @patch("windowspc_mcp.display.setup.urllib.request.urlopen")
    def test_returns_first_match(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen(
            _github_payload("a-portable.zip", "b-portable.zip")
        )
        assert _find_portable_zip_url() == "https://example.com/a-portable.zip"


# =========================================================================
# _download_and_extract
# =========================================================================


class TestDownloadAndExtract:
    """Success path and cleanup on failure."""

    @patch("windowspc_mcp.display.setup.zipfile.ZipFile")
    @patch("windowspc_mcp.display.setup.urllib.request.urlretrieve")
    @patch("windowspc_mcp.display.setup.shutil.rmtree")
    @patch("windowspc_mcp.display.setup.tempfile.NamedTemporaryFile")
    @patch.object(Path, "unlink")
    @patch.object(Path, "mkdir")
    @patch.object(Path, "exists", return_value=True)
    @patch.object(Path, "stat")
    def test_success(
        self, mock_stat, mock_exists, mock_mkdir, mock_unlink,
        mock_tmpfile, mock_rmtree, mock_retrieve, mock_zipfile,
    ):
        mock_stat.return_value = MagicMock(st_size=102400)

        tmp = MagicMock()
        tmp.name = "C:\\tmp\\dl.zip"
        tmp.__enter__ = MagicMock(return_value=tmp)
        tmp.__exit__ = MagicMock(return_value=False)
        mock_tmpfile.return_value = tmp

        zf = MagicMock()
        zf.__enter__ = MagicMock(return_value=zf)
        zf.__exit__ = MagicMock(return_value=False)
        mock_zipfile.return_value = zf

        result = _download_and_extract("https://example.com/driver-portable.zip")
        assert result == _VDD_DIR
        mock_retrieve.assert_called_once()
        zf.extractall.assert_called_once_with(_VDD_DIR)
        mock_unlink.assert_called()

    @patch("windowspc_mcp.display.setup.urllib.request.urlretrieve", side_effect=OSError("net err"))
    @patch("windowspc_mcp.display.setup.tempfile.NamedTemporaryFile")
    @patch.object(Path, "unlink")
    @patch.object(Path, "mkdir")
    def test_cleanup_on_failure(self, mock_mkdir, mock_unlink, mock_tmpfile, mock_retrieve):
        tmp = MagicMock()
        tmp.name = "C:\\tmp\\dl.zip"
        tmp.__enter__ = MagicMock(return_value=tmp)
        tmp.__exit__ = MagicMock(return_value=False)
        mock_tmpfile.return_value = tmp

        with pytest.raises(OSError, match="net err"):
            _download_and_extract("https://example.com/driver-portable.zip")
        # finally block should still unlink temp file
        mock_unlink.assert_called()

    @patch("windowspc_mcp.display.setup.zipfile.ZipFile")
    @patch("windowspc_mcp.display.setup.urllib.request.urlretrieve")
    @patch("windowspc_mcp.display.setup.shutil.rmtree")
    @patch("windowspc_mcp.display.setup.tempfile.NamedTemporaryFile")
    @patch.object(Path, "unlink")
    @patch.object(Path, "mkdir")
    @patch.object(Path, "exists", return_value=False)
    @patch.object(Path, "stat")
    def test_skips_rmtree_when_not_exists(
        self, mock_stat, mock_exists, mock_mkdir, mock_unlink,
        mock_tmpfile, mock_rmtree, mock_retrieve, mock_zipfile,
    ):
        mock_stat.return_value = MagicMock(st_size=1024)

        tmp = MagicMock()
        tmp.name = "C:\\tmp\\dl.zip"
        tmp.__enter__ = MagicMock(return_value=tmp)
        tmp.__exit__ = MagicMock(return_value=False)
        mock_tmpfile.return_value = tmp

        zf = MagicMock()
        zf.__enter__ = MagicMock(return_value=zf)
        zf.__exit__ = MagicMock(return_value=False)
        mock_zipfile.return_value = zf

        _download_and_extract("https://example.com/driver.zip")
        mock_rmtree.assert_not_called()


# =========================================================================
# _find_nefconw
# =========================================================================


class TestFindNefconw:
    """Found and not-found paths."""

    def test_found(self, tmp_path):
        nef = tmp_path / "sub" / "nefconw.exe"
        nef.parent.mkdir()
        nef.touch()
        assert _find_nefconw(tmp_path) == nef

    def test_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="nefconw.exe not found"):
            _find_nefconw(tmp_path)


# =========================================================================
# _find_inf
# =========================================================================


class TestFindInf:
    """Found and not-found paths."""

    def test_found(self, tmp_path):
        inf = tmp_path / "drv" / "mm.inf"
        inf.parent.mkdir()
        inf.touch()
        assert _find_inf(tmp_path) == inf

    def test_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="mm.inf not found"):
            _find_inf(tmp_path)


# =========================================================================
# _install_driver
# =========================================================================


class TestInstallDriver:
    """All 3 steps succeed, step 1 fail tolerated, step 2/3 fail raises."""

    def _make_paths(self, tmp_path):
        nef = tmp_path / "nefconw.exe"
        inf = tmp_path / "drv" / "mm.inf"
        nef.touch()
        inf.parent.mkdir(parents=True, exist_ok=True)
        inf.touch()
        return nef, inf

    @patch("ctypes.windll")
    def test_all_succeed(self, mock_windll, tmp_path):
        nef, inf = self._make_paths(tmp_path)
        mock_windll.shell32.ShellExecuteW.return_value = 42
        _install_driver(nef, inf)
        assert mock_windll.shell32.ShellExecuteW.call_count == 3

    @patch("ctypes.windll")
    def test_step1_fail_tolerated(self, mock_windll, tmp_path):
        nef, inf = self._make_paths(tmp_path)
        mock_windll.shell32.ShellExecuteW.side_effect = [5, 42, 42]
        _install_driver(nef, inf)  # no exception
        assert mock_windll.shell32.ShellExecuteW.call_count == 3

    @patch("ctypes.windll")
    def test_step2_fail_raises(self, mock_windll, tmp_path):
        nef, inf = self._make_paths(tmp_path)
        mock_windll.shell32.ShellExecuteW.side_effect = [42, 5]
        with pytest.raises(RuntimeError, match="step 2 failed"):
            _install_driver(nef, inf)

    @patch("ctypes.windll")
    def test_step3_fail_raises(self, mock_windll, tmp_path):
        nef, inf = self._make_paths(tmp_path)
        mock_windll.shell32.ShellExecuteW.side_effect = [42, 42, 0]
        with pytest.raises(RuntimeError, match="step 3 failed"):
            _install_driver(nef, inf)

    @patch("ctypes.windll")
    def test_runas_verb_used(self, mock_windll, tmp_path):
        nef, inf = self._make_paths(tmp_path)
        mock_windll.shell32.ShellExecuteW.return_value = 42
        _install_driver(nef, inf)
        for c in mock_windll.shell32.ShellExecuteW.call_args_list:
            assert c[0][1] == "runas"

    @patch("ctypes.windll")
    def test_correct_exe_path(self, mock_windll, tmp_path):
        nef, inf = self._make_paths(tmp_path)
        mock_windll.shell32.ShellExecuteW.return_value = 42
        _install_driver(nef, inf)
        for c in mock_windll.shell32.ShellExecuteW.call_args_list:
            assert c[0][2] == str(nef)
            assert c[0][4] == str(nef.parent)


# =========================================================================
# ensure_driver_installed
# =========================================================================


class TestEnsureDriverInstalled:
    """Already present, install+verify success, install fails, verify fails."""

    @patch("windowspc_mcp.display.driver.CloseHandle")
    @patch("windowspc_mcp.display.driver.open_device_handle")
    def test_already_present(self, mock_open, mock_close):
        mock_open.return_value = MagicMock()
        assert ensure_driver_installed() is True
        mock_open.assert_called_once()
        mock_close.assert_called_once()

    @patch("time.sleep")
    @patch("windowspc_mcp.display.setup._install_driver")
    @patch("windowspc_mcp.display.setup._find_inf")
    @patch("windowspc_mcp.display.setup._find_nefconw")
    @patch("windowspc_mcp.display.setup._download_and_extract")
    @patch("windowspc_mcp.display.setup._find_portable_zip_url")
    @patch("windowspc_mcp.display.driver.CloseHandle")
    @patch("windowspc_mcp.display.driver.open_device_handle")
    def test_install_and_verify_success(
        self, mock_open, mock_close, mock_url, mock_dl, mock_nef, mock_inf, mock_inst, mock_sleep,
    ):
        handle = MagicMock()
        mock_open.side_effect = [OSError("no"), handle]
        mock_url.return_value = "https://example.com/d-portable.zip"
        mock_dl.return_value = Path("C:/vdd")
        mock_nef.return_value = Path("C:/vdd/nefconw.exe")
        mock_inf.return_value = Path("C:/vdd/mm.inf")

        assert ensure_driver_installed() is True
        mock_inst.assert_called_once()
        mock_sleep.assert_called_once_with(3)
        assert mock_open.call_count == 2

    @patch("windowspc_mcp.display.setup._find_portable_zip_url")
    @patch("windowspc_mcp.display.driver.CloseHandle")
    @patch("windowspc_mcp.display.driver.open_device_handle")
    def test_install_fails(self, mock_open, mock_close, mock_url):
        mock_open.side_effect = OSError("no")
        mock_url.side_effect = RuntimeError("no zip")
        assert ensure_driver_installed() is False

    @patch("time.sleep")
    @patch("windowspc_mcp.display.setup._install_driver")
    @patch("windowspc_mcp.display.setup._find_inf")
    @patch("windowspc_mcp.display.setup._find_nefconw")
    @patch("windowspc_mcp.display.setup._download_and_extract")
    @patch("windowspc_mcp.display.setup._find_portable_zip_url")
    @patch("windowspc_mcp.display.driver.CloseHandle")
    @patch("windowspc_mcp.display.driver.open_device_handle")
    def test_verify_fails(
        self, mock_open, mock_close, mock_url, mock_dl, mock_nef, mock_inf, mock_inst, mock_sleep,
    ):
        mock_open.side_effect = [OSError("no"), OSError("still no")]
        mock_url.return_value = "https://example.com/d-portable.zip"
        mock_dl.return_value = Path("C:/vdd")
        mock_nef.return_value = Path("C:/vdd/nefconw.exe")
        mock_inf.return_value = Path("C:/vdd/mm.inf")

        assert ensure_driver_installed() is False
        assert mock_open.call_count == 2
        mock_close.assert_not_called()

    @patch("windowspc_mcp.display.setup._download_and_extract")
    @patch("windowspc_mcp.display.setup._find_portable_zip_url")
    @patch("windowspc_mcp.display.driver.CloseHandle")
    @patch("windowspc_mcp.display.driver.open_device_handle")
    def test_download_fails(self, mock_open, mock_close, mock_url, mock_dl):
        mock_open.side_effect = OSError("no")
        mock_url.return_value = "https://example.com/d-portable.zip"
        mock_dl.side_effect = OSError("network fail")
        assert ensure_driver_installed() is False

    @patch("windowspc_mcp.display.setup._install_driver")
    @patch("windowspc_mcp.display.setup._find_inf")
    @patch("windowspc_mcp.display.setup._find_nefconw")
    @patch("windowspc_mcp.display.setup._download_and_extract")
    @patch("windowspc_mcp.display.setup._find_portable_zip_url")
    @patch("windowspc_mcp.display.driver.CloseHandle")
    @patch("windowspc_mcp.display.driver.open_device_handle")
    def test_install_driver_runtime_error(
        self, mock_open, mock_close, mock_url, mock_dl, mock_nef, mock_inf, mock_inst,
    ):
        mock_open.side_effect = OSError("no")
        mock_url.return_value = "https://example.com/d-portable.zip"
        mock_dl.return_value = Path("C:/vdd")
        mock_nef.return_value = Path("C:/vdd/nefconw.exe")
        mock_inf.return_value = Path("C:/vdd/mm.inf")
        mock_inst.side_effect = RuntimeError("step 2 failed")

        assert ensure_driver_installed() is False
        mock_close.assert_not_called()
