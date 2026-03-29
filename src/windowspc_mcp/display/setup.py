"""Auto-download and install the Parsec VDD driver if not already present."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path

log = logging.getLogger(__name__)

_VDD_DIR = Path.home() / ".windowspc-mcp" / "vdd"

_RELEASES_URL = "https://api.github.com/repos/nomi-san/parsec-vdd/releases/latest"

# Display device class GUID (standard Windows constant)
_DISPLAY_CLASS_GUID = "{4D36E968-E325-11CE-BFC1-08002BE10318}"
_HARDWARE_ID = r"Root\Parsec\VDA"


def _find_portable_zip_url() -> str:
    """Query GitHub releases API for the portable ZIP download URL."""
    import json

    req = urllib.request.Request(
        _RELEASES_URL,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "WindowsPC-MCP"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())

    for asset in data.get("assets", []):
        name: str = asset.get("name", "")
        if name.endswith("-portable.zip"):
            return asset["browser_download_url"]

    raise RuntimeError(
        "Could not find portable ZIP in the latest parsec-vdd release. "
        "Please install manually: https://github.com/nomi-san/parsec-vdd/releases"
    )


def _download_and_extract(url: str) -> Path:
    """Download the portable ZIP and extract to _VDD_DIR. Returns the extraction root."""
    _VDD_DIR.mkdir(parents=True, exist_ok=True)

    log.info("Downloading Parsec VDD from %s", url)
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        urllib.request.urlretrieve(url, str(tmp_path))
        log.info("Download complete (%d KB)", tmp_path.stat().st_size // 1024)

        # Clear old extraction if present
        if _VDD_DIR.exists():
            shutil.rmtree(_VDD_DIR)
        _VDD_DIR.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(tmp_path, "r") as zf:
            zf.extractall(_VDD_DIR)

        log.info("Extracted to %s", _VDD_DIR)
    finally:
        tmp_path.unlink(missing_ok=True)

    return _VDD_DIR


def _find_nefconw(base: Path) -> Path:
    """Locate nefconw.exe under the extraction directory."""
    candidates = list(base.rglob("nefconw.exe"))
    if not candidates:
        raise FileNotFoundError(
            f"nefconw.exe not found under {base}. "
            "The Parsec VDD release format may have changed."
        )
    return candidates[0]


def _find_inf(base: Path) -> Path:
    """Locate mm.inf under the extraction directory."""
    candidates = list(base.rglob("mm.inf"))
    if not candidates:
        raise FileNotFoundError(
            f"mm.inf not found under {base}. "
            "The Parsec VDD release format may have changed."
        )
    return candidates[0]


def _install_driver(nefconw: Path, inf: Path) -> None:
    """Run the three nefconw commands elevated via ShellExecuteW (triggers UAC).

    The commands are:
      1. Remove any existing device node
      2. Create a new device node
      3. Install the driver from the .inf
    """
    import ctypes

    shell32 = ctypes.windll.shell32

    commands = [
        # Step 1: remove old device node (may fail if none exists — that's OK)
        (
            str(nefconw),
            f"--remove-device-node --hardware-id {_HARDWARE_ID} "
            f"--class-guid {_DISPLAY_CLASS_GUID}",
        ),
        # Step 2: create device node
        (
            str(nefconw),
            f"--create-device-node --class-name Display "
            f"--class-guid {_DISPLAY_CLASS_GUID} --hardware-id {_HARDWARE_ID}",
        ),
        # Step 3: install the driver
        (
            str(nefconw),
            f'--install-driver --inf-path "{inf}"',
        ),
    ]

    for i, (exe, params) in enumerate(commands, 1):
        log.info("VDD install step %d/3: %s %s", i, exe, params)
        # ShellExecuteW with "runas" triggers UAC elevation
        result = shell32.ShellExecuteW(None, "runas", exe, params, str(nefconw.parent), 0)
        if result <= 32:
            if i == 1:
                # Step 1 failure is expected if no prior device node exists
                log.debug("Step 1 (remove old node) returned %d — probably no prior install", result)
            else:
                raise RuntimeError(
                    f"VDD install step {i} failed (ShellExecuteW returned {result}). "
                    "You may need to install the Parsec VDD driver manually."
                )


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
        url = _find_portable_zip_url()
        base = _download_and_extract(url)
        nefconw = _find_nefconw(base)
        inf = _find_inf(base)
        _install_driver(nefconw, inf)
    except Exception:
        log.exception("Automatic VDD driver installation failed")
        return False

    # Give Windows a moment to register the new driver
    import time
    time.sleep(3)

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
