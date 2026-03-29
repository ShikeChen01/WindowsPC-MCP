"""Smoke: download the real Parsec VDD release and verify contents.

No mocks — actually hits GitHub API and downloads the file.
"""

import pytest
import shutil
from pathlib import Path

from windowspc_mcp.display.setup import _find_setup_exe_url, _download_setup, _VDD_DIR


@pytest.fixture
def clean_vdd_dir():
    """Ensure _VDD_DIR is clean before and after test."""
    backup = None
    if _VDD_DIR.exists():
        backup = _VDD_DIR.parent / "vdd_backup"
        shutil.move(str(_VDD_DIR), str(backup))
    yield _VDD_DIR
    # Restore
    if _VDD_DIR.exists():
        shutil.rmtree(_VDD_DIR)
    if backup and backup.exists():
        shutil.move(str(backup), str(_VDD_DIR))


@pytest.mark.network
class TestFindSetupExeUrlReal:
    """Hit the real GitHub API."""

    def test_returns_valid_url(self):
        url = _find_setup_exe_url()
        assert url.startswith("https://")
        assert "github.com" in url
        assert url.endswith(".exe")

    def test_url_contains_parsec(self):
        url = _find_setup_exe_url()
        filename = url.rsplit("/", 1)[-1].lower()
        assert "parsec" in filename or "vdd" in filename or "setup" in filename


@pytest.mark.network
class TestDownloadSetupReal:
    """Actually download the setup EXE."""

    def test_download_produces_exe(self, clean_vdd_dir):
        url = _find_setup_exe_url()
        path = _download_setup(url)
        assert path.exists()
        assert path.stat().st_size > 100_000  # should be > 100KB
        assert path.suffix == ".exe"

    def test_downloaded_file_has_mz_header(self, clean_vdd_dir):
        """Verify it's a real PE executable, not an HTML error page."""
        url = _find_setup_exe_url()
        path = _download_setup(url)
        with open(path, "rb") as f:
            header = f.read(2)
        assert header == b"MZ", f"Expected PE header 'MZ', got {header!r}"
