"""Virtual display lifecycle management using Parsec VDD."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DisplayInfo dataclass
# ---------------------------------------------------------------------------


@dataclass
class DisplayInfo:
    """Represents a physical or virtual monitor and its screen-space bounds."""

    device_name: str
    x: int
    y: int
    width: int
    height: int
    is_agent: bool = False

    # ------------------------------------------------------------------
    # Boundary properties
    # ------------------------------------------------------------------

    @property
    def left(self) -> int:
        return self.x

    @property
    def top(self) -> int:
        return self.y

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    # ------------------------------------------------------------------
    # Coordinate helpers
    # ------------------------------------------------------------------

    def contains_point(self, px: int, py: int) -> bool:
        """Return True if (px, py) is inside this display (inclusive left/top, exclusive right/bottom)."""
        return self.left <= px < self.right and self.top <= py < self.bottom

    def to_relative(self, abs_x: int, abs_y: int) -> tuple[int, int]:
        """Convert absolute screen coordinates to display-relative coordinates."""
        return abs_x - self.x, abs_y - self.y

    def to_absolute(self, rel_x: int, rel_y: int) -> tuple[int, int]:
        """Convert display-relative coordinates to absolute screen coordinates."""
        return rel_x + self.x, rel_y + self.y


# ---------------------------------------------------------------------------
# DisplayManager
# ---------------------------------------------------------------------------


class DisplayManager:
    """Manages the lifecycle of a Parsec VDD virtual display."""

    def __init__(self) -> None:
        self._vdd = None
        self._agent_display: Optional[DisplayInfo] = None
        self._display_index: Optional[int] = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def agent_display(self) -> Optional[DisplayInfo]:
        """Return the current agent (virtual) display, or None if not active."""
        return self._agent_display

    @property
    def is_ready(self) -> bool:
        """Return True if an agent display is active."""
        return self._agent_display is not None

    # ------------------------------------------------------------------
    # Driver check
    # ------------------------------------------------------------------

    def check_driver(self) -> bool:
        """Return True if the Parsec VDD driver is present and accessible."""
        try:
            from windowspc_mcp.display.driver import ParsecVDD

            vdd = ParsecVDD()
            vdd.close()
            return True
        except Exception as exc:
            log.debug("check_driver failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Display creation
    # ------------------------------------------------------------------

    def create_display(self, width: int = 1920, height: int = 1080) -> DisplayInfo:
        """Create a virtual display and return its DisplayInfo.

        Raises RuntimeError if an agent display already exists.
        Attempts crash-recovery if a stale state file is found.
        """
        if self._agent_display is not None:
            raise RuntimeError("Agent display already exists; destroy it first.")

        from windowspc_mcp.display.driver import ParsecVDD
        from windowspc_mcp.display.identity import load_state, save_state, clear_state, PersistedDisplayState

        # ---- crash recovery ----
        saved = load_state()
        if saved is not None:
            log.info("Found persisted display state for %s – attempting reconnect", saved.device_name)
            existing = self._find_display_by_name(saved.device_name)
            if existing is not None:
                log.info("Reconnected to existing virtual display %s", saved.device_name)
                existing.is_agent = True
                self._agent_display = existing
                self._display_index = saved.display_index
                # Re-open VDD for keepalive (best-effort)
                try:
                    self._vdd = ParsecVDD()
                except Exception:
                    pass
                return existing
            else:
                log.info("Persisted display no longer present; clearing stale state")
                clear_state()

        # ---- fresh creation ----
        self._vdd = ParsecVDD()
        before = {d.device_name for d in self.enumerate_monitors()}

        self._display_index = self._vdd.add_display()
        log.debug("VDD add_display() -> index %d", self._display_index)

        # Wait for Windows to enumerate the new monitor
        time.sleep(1.0)

        new_display = self._find_new_display(before)
        if new_display is None:
            raise RuntimeError("New virtual display did not appear after add_display()")

        # Set resolution
        self._set_resolution(new_display.device_name, width, height)

        # Wait for resolution change to settle
        time.sleep(0.5)

        # Re-enumerate to get final bounds
        final = self._find_display_by_name(new_display.device_name)
        if final is None:
            final = new_display
        final.is_agent = True
        self._agent_display = final

        # Persist state for crash recovery
        save_state(
            PersistedDisplayState(
                device_name=final.device_name,
                display_index=self._display_index,
                width=final.width,
                height=final.height,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        )

        log.info(
            "Created agent display %s at (%d,%d) %dx%d",
            final.device_name,
            final.x,
            final.y,
            final.width,
            final.height,
        )
        return final

    # ------------------------------------------------------------------
    # Display destruction
    # ------------------------------------------------------------------

    def destroy_display(self) -> None:
        """Migrate windows, remove the virtual display, and clean up state."""
        from windowspc_mcp.display.identity import clear_state

        if self._agent_display is not None:
            self._migrate_windows_to_primary()
            self._agent_display = None

        if self._vdd is not None and self._display_index is not None:
            try:
                self._vdd.remove_display(self._display_index)
            except Exception as exc:
                log.warning("Error removing virtual display: %s", exc)
            self._display_index = None

        if self._vdd is not None:
            try:
                self._vdd.close()
            except Exception as exc:
                log.warning("Error closing VDD: %s", exc)
            self._vdd = None

        clear_state()
        log.info("Agent display destroyed and state cleared")

    # ------------------------------------------------------------------
    # Monitor enumeration
    # ------------------------------------------------------------------

    def enumerate_monitors(self) -> list[DisplayInfo]:
        """Return a list of DisplayInfo for all currently active monitors."""
        try:
            import win32api
            import win32con
        except ImportError:
            log.warning("win32api not available; returning empty monitor list")
            return []

        monitors: list[DisplayInfo] = []
        try:
            raw = win32api.EnumDisplayMonitors(None, None)
        except Exception as exc:
            log.warning("EnumDisplayMonitors failed: %s", exc)
            return []

        for hmonitor, _hdc, rect in raw:
            # rect is (left, top, right, bottom)
            left, top, right, bottom = rect
            device_name = self._device_name_for_rect(left, top, right, bottom)
            monitors.append(
                DisplayInfo(
                    device_name=device_name or "",
                    x=left,
                    y=top,
                    width=right - left,
                    height=bottom - top,
                )
            )

        return monitors

    def refresh_bounds(self) -> None:
        """Re-enumerate monitors and update agent_display bounds."""
        if self._agent_display is None:
            return
        updated = self._find_display_by_name(self._agent_display.device_name)
        if updated is not None:
            updated.is_agent = True
            self._agent_display = updated

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _find_new_display(self, before: set[str]) -> Optional[DisplayInfo]:
        """Return the first new monitor whose DeviceString contains 'ParsecVDA'."""
        try:
            import win32api
            import win32con
        except ImportError:
            return None

        for monitor in self.enumerate_monitors():
            if monitor.device_name in before:
                continue
            # Confirm it's a Parsec virtual display
            try:
                dev_info = win32api.EnumDisplayDevices(monitor.device_name, 0, 0)
                if "ParsecVDA" in (dev_info.DeviceString or ""):
                    return monitor
            except Exception:
                # If we can't query, still return any new display
                return monitor

        # Fallback: return any new display regardless of DeviceString
        for monitor in self.enumerate_monitors():
            if monitor.device_name not in before:
                return monitor

        return None

    def _find_display_by_name(self, device_name: str) -> Optional[DisplayInfo]:
        """Return the DisplayInfo for a monitor with the given device name, or None."""
        for monitor in self.enumerate_monitors():
            if monitor.device_name == device_name:
                return monitor
        return None

    def _device_name_for_rect(
        self, left: int, top: int, right: int, bottom: int
    ) -> Optional[str]:
        """Return the Win32 device name (e.g. '\\\\.\\DISPLAY3') for a monitor rect."""
        try:
            import win32api

            idx = 0
            while True:
                try:
                    dev = win32api.EnumDisplayDevices(None, idx, 0)
                except Exception:
                    break
                if not dev.DeviceName:
                    break
                try:
                    settings = win32api.EnumDisplaySettings(dev.DeviceName, -1)  # ENUM_CURRENT_SETTINGS
                    ml = settings.Position_x
                    mt = settings.Position_y
                    mr = ml + settings.PelsWidth
                    mb = mt + settings.PelsHeight
                    if ml == left and mt == top and mr == right and mb == bottom:
                        return dev.DeviceName
                except Exception:
                    pass
                idx += 1
        except Exception as exc:
            log.debug("_device_name_for_rect failed: %s", exc)
        return None

    def _set_resolution(self, device_name: str, width: int, height: int) -> None:
        """Set the resolution of a display via ChangeDisplaySettingsEx."""
        try:
            import win32api
            import win32con
            import pywintypes

            dm = win32api.EnumDisplaySettings(device_name, -1)
            dm.PelsWidth = width
            dm.PelsHeight = height
            dm.Fields = win32con.DM_PELSWIDTH | win32con.DM_PELSHEIGHT
            result = win32api.ChangeDisplaySettingsEx(device_name, dm, win32con.CDS_UPDATEREGISTRY)
            if result != 0:
                log.warning(
                    "ChangeDisplaySettingsEx returned %d for %s", result, device_name
                )
            else:
                log.debug("Resolution set to %dx%d on %s", width, height, device_name)
        except Exception as exc:
            log.warning("_set_resolution failed for %s: %s", device_name, exc)

    def _migrate_windows_to_primary(self) -> None:
        """Move all windows on the agent display to the primary monitor."""
        if self._agent_display is None:
            return

        try:
            from windowspc_mcp.uia.controls import (
                enumerate_windows,
                get_window_rect,
                move_window,
                is_window_visible,
            )

            primary = self._get_primary_display()
            target_x = primary.x if primary else 0
            target_y = primary.y if primary else 0

            for hwnd in enumerate_windows():
                if not is_window_visible(hwnd):
                    continue
                rect = get_window_rect(hwnd)
                if rect is None:
                    continue
                wx, wy, ww, wh = rect
                # Check if window centre is on the agent display
                cx, cy = wx + ww // 2, wy + wh // 2
                if self._agent_display.contains_point(cx, cy):
                    move_window(hwnd, target_x, target_y, ww, wh)
                    log.debug("Migrated hwnd %d to primary display", hwnd)
        except Exception as exc:
            log.warning("_migrate_windows_to_primary failed: %s", exc)

    def _get_primary_display(self) -> Optional[DisplayInfo]:
        """Return the primary display (the one at origin 0,0), if any."""
        for monitor in self.enumerate_monitors():
            if monitor.x == 0 and monitor.y == 0:
                return monitor
        monitors = self.enumerate_monitors()
        return monitors[0] if monitors else None
