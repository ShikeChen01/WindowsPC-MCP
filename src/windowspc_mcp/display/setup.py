"""Auto-download and install the Parsec VDD driver if not already present."""

from __future__ import annotations

import logging
import subprocess
import tempfile
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)

_VDD_DIR = Path.home() / ".windowspc-mcp" / "vdd"

_RELEASES_URL = "https://api.github.com/repos/nomi-san/parsec-vdd/releases/latest"


def _find_setup_exe_url() -> str:
    """Query GitHub releases API for the setup EXE download URL."""
    import json

    req = urllib.request.Request(
        _RELEASES_URL,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "WindowsPC-MCP"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())

    for asset in data.get("assets", []):
        name: str = asset.get("name", "")
        if name.endswith("-setup.exe") or name.endswith(".exe") and "setup" in name.lower():
            return asset["browser_download_url"]

    raise RuntimeError(
        "Could not find setup EXE in the latest parsec-vdd release. "
        "Please install manually: https://github.com/nomi-san/parsec-vdd/releases"
    )


def _download_setup(url: str) -> Path:
    """Download the setup EXE to _VDD_DIR. Returns the path to the EXE."""
    _VDD_DIR.mkdir(parents=True, exist_ok=True)

    # Derive filename from URL
    filename = url.rsplit("/", 1)[-1]
    dest = _VDD_DIR / filename

    log.info("Downloading Parsec VDD from %s", url)
    urllib.request.urlretrieve(url, str(dest))
    log.info("Download complete (%d KB)", dest.stat().st_size // 1024)

    return dest


def _install_driver(setup_exe: Path) -> None:
    """Run the Parsec VDD setup EXE with /S (silent) elevated via ShellExecuteW.

    The Inno Setup installer accepts /S (or /SILENT /VERYSILENT) for unattended
    installation. ShellExecuteW with "runas" triggers a UAC prompt.
    """
    import ctypes

    shell32 = ctypes.windll.shell32

    log.info("Installing Parsec VDD driver (UAC prompt will appear): %s", setup_exe)
    # ShellExecuteW with "runas" triggers UAC elevation
    # /VERYSILENT suppresses all UI; /NORESTART avoids reboots
    result = shell32.ShellExecuteW(
        None, "runas", str(setup_exe), "/VERYSILENT /NORESTART", str(setup_exe.parent), 0
    )
    if result <= 32:
        raise RuntimeError(
            f"VDD installer failed (ShellExecuteW returned {result}). "
            "You may need to install the Parsec VDD driver manually."
        )

    # ShellExecuteW returns immediately; wait for the installer to finish
    import time
    log.info("Waiting for installer to complete...")
    time.sleep(10)


def ensure_driver_installed() -> bool:
    """Check for the Parsec VDD driver and install it if missing.

    Returns True if the driver is available (either already was, or was
    successfully installed). Returns False if installation failed or was
    declined by the user.
    """
    from windowspc_mcp.display.driver import open_device_handle, CloseHandle

    # Quick check: is the driver already present?
    try:
        handle = open_device_handle()
        CloseHandle(handle)
        log.info("Parsec VDD driver already installed")
        return True
    except OSError:
        pass

    log.info("Parsec VDD driver not found — starting automatic setup")

    try:
        url = _find_setup_exe_url()
        setup_exe = _download_setup(url)
        _install_driver(setup_exe)
    except Exception:
        log.exception("Automatic VDD driver installation failed")
        return False

    # Verify
    try:
        handle = open_device_handle()
        CloseHandle(handle)
        log.info("Parsec VDD driver installed and verified successfully")
        return True
    except OSError:
        log.warning(
            "VDD driver install appeared to succeed but device is not yet available. "
            "A reboot may be required."
        )
        return False
