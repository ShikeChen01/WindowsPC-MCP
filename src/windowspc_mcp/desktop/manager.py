"""Win32 desktop isolation for the agent.

Creates, switches, and destroys a dedicated Windows desktop so the agent's
SendInput calls are isolated from the user's interactive session.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import subprocess
import threading
from ctypes import POINTER, c_void_p
from types import TracebackType

from windowspc_mcp.confinement.errors import InvalidStateError, WindowsMCPError

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom errors
# ---------------------------------------------------------------------------


class DesktopError(WindowsMCPError):
    """Failure in desktop creation, switching, or teardown."""


# ---------------------------------------------------------------------------
# Win32 type aliases
# ---------------------------------------------------------------------------

HDESK = ctypes.wintypes.HANDLE  # desktop handle

# ---------------------------------------------------------------------------
# Win32 constants
# ---------------------------------------------------------------------------

DESKTOP_ALL_ACCESS = 0x01FF
GENERIC_ALL = 0x10000000
DF_ALLOWOTHERACCOUNTHOOK = 0x0001

# ---------------------------------------------------------------------------
# Win32 API bindings — user32
# ---------------------------------------------------------------------------

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# HDESK CreateDesktopW(LPCWSTR, LPCWSTR, DEVMODE*, DWORD, DWORD, SECURITY_ATTRIBUTES*)
user32.CreateDesktopW.restype = HDESK
user32.CreateDesktopW.argtypes = [
    ctypes.wintypes.LPCWSTR,  # lpszDesktop
    ctypes.wintypes.LPCWSTR,  # lpszDevice (NULL)
    c_void_p,                 # pDevmode (NULL)
    ctypes.wintypes.DWORD,    # dwFlags
    ctypes.wintypes.DWORD,    # dwDesiredAccess
    c_void_p,                 # lpsa (NULL)
]

# BOOL SwitchDesktop(HDESK)
user32.SwitchDesktop.restype = ctypes.wintypes.BOOL
user32.SwitchDesktop.argtypes = [HDESK]

# BOOL CloseDesktop(HDESK)
user32.CloseDesktop.restype = ctypes.wintypes.BOOL
user32.CloseDesktop.argtypes = [HDESK]

# HDESK OpenInputDesktop(DWORD, BOOL, DWORD)
user32.OpenInputDesktop.restype = HDESK
user32.OpenInputDesktop.argtypes = [
    ctypes.wintypes.DWORD,  # dwFlags
    ctypes.wintypes.BOOL,   # fInherit
    ctypes.wintypes.DWORD,  # dwDesiredAccess
]

# HDESK GetThreadDesktop(DWORD)
user32.GetThreadDesktop.restype = HDESK
user32.GetThreadDesktop.argtypes = [ctypes.wintypes.DWORD]

# BOOL SetThreadDesktop(HDESK)
user32.SetThreadDesktop.restype = ctypes.wintypes.BOOL
user32.SetThreadDesktop.argtypes = [HDESK]

# ---------------------------------------------------------------------------
# Win32 API bindings — kernel32
# ---------------------------------------------------------------------------

# DWORD GetCurrentThreadId(void)
kernel32.GetCurrentThreadId.restype = ctypes.wintypes.DWORD
kernel32.GetCurrentThreadId.argtypes = []

# ---------------------------------------------------------------------------
# DesktopManager
# ---------------------------------------------------------------------------

_AGENT_DESKTOP_NAME = "WindowsPC_MCP_Agent"


class DesktopManager:
    """Create, switch, and destroy an isolated Windows desktop for the agent.

    Thread-safe: all public methods are serialised through an internal lock.
    """

    def __init__(self) -> None:
        """Capture the user's current desktop handle.  Do not create the agent
        desktop yet — call :meth:`create_agent_desktop` explicitly."""
        self._lock = threading.Lock()
        self._user_desktop: HDESK | None = None
        self._agent_desktop: HDESK | None = None
        self._agent_is_active: bool = False
        self._processes: list[subprocess.Popen] = []

        # Capture the current thread's desktop as the "user" desktop.
        tid = kernel32.GetCurrentThreadId()
        hdesk = user32.GetThreadDesktop(tid)
        if not hdesk:
            raise DesktopError(
                f"GetThreadDesktop failed (thread {tid}), "
                f"error {ctypes.get_last_error()}"
            )
        self._user_desktop = hdesk
        log.debug("Captured user desktop handle: %s (thread %d)", hdesk, tid)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_agent_desktop(self) -> None:
        """Create the agent desktop.  Raises if it already exists."""
        with self._lock:
            if self._agent_desktop is not None:
                raise InvalidStateError("Agent desktop already exists")

            hdesk = user32.CreateDesktopW(
                _AGENT_DESKTOP_NAME,
                None,   # lpszDevice
                None,   # pDevmode
                0,      # dwFlags
                DESKTOP_ALL_ACCESS,
                None,   # lpsa
            )
            if not hdesk:
                err = ctypes.get_last_error()
                raise DesktopError(
                    f"CreateDesktopW failed for '{_AGENT_DESKTOP_NAME}', "
                    f"error {err}"
                )
            self._agent_desktop = hdesk
            log.info("Created agent desktop '%s' (handle %s)",
                     _AGENT_DESKTOP_NAME, hdesk)

    def switch_to_agent(self) -> None:
        """Make the agent desktop the input desktop."""
        with self._lock:
            if self._agent_desktop is None:
                raise InvalidStateError("Agent desktop has not been created")
            if self._agent_is_active:
                log.debug("Agent desktop already active — no-op")
                return
            if not user32.SwitchDesktop(self._agent_desktop):
                raise DesktopError(
                    f"SwitchDesktop(agent) failed, error {ctypes.get_last_error()}"
                )
            self._agent_is_active = True
            log.info("Switched input to agent desktop")

    def switch_to_user(self) -> None:
        """Make the user's desktop the input desktop."""
        with self._lock:
            self._switch_to_user_unlocked()

    def launch_on_agent(
        self,
        executable: str,
        args: list[str] | None = None,
        cwd: str | None = None,
    ) -> int:
        """Launch a process on the agent desktop.

        Sets ``STARTUPINFO.lpDesktop`` so the new process's windows appear on
        the agent desktop.  Returns the PID of the new process.
        """
        with self._lock:
            if self._agent_desktop is None:
                raise InvalidStateError("Agent desktop has not been created")

            desktop_name = _AGENT_DESKTOP_NAME
            cmd = [executable] + (args or [])

            si = subprocess.STARTUPINFO()
            si.lpDesktop = desktop_name  # type: ignore[attr-defined]

            proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                startupinfo=si,
            )
            self._processes.append(proc)
            log.info(
                "Launched %s on agent desktop (PID %d)", executable, proc.pid
            )
            return proc.pid

    def destroy(self) -> None:
        """Close the agent desktop handle.

        Terminates any still-running processes launched on the agent desktop,
        switches back to the user's desktop if needed, and closes the handle.
        """
        with self._lock:
            if self._agent_desktop is None:
                log.debug("destroy() called but no agent desktop exists — no-op")
                return

            # Terminate any still-running processes.
            for proc in self._processes:
                if proc.poll() is None:
                    log.info("Terminating agent process PID %d", proc.pid)
                    try:
                        proc.terminate()
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        log.warning("Killing agent process PID %d", proc.pid)
                        proc.kill()
                        proc.wait(timeout=3)
                    except OSError:
                        pass
            self._processes.clear()

            # Switch back to user desktop first if agent is active.
            if self._agent_is_active:
                self._switch_to_user_unlocked()

            if not user32.CloseDesktop(self._agent_desktop):
                log.warning(
                    "CloseDesktop failed, error %d", ctypes.get_last_error()
                )
            else:
                log.info("Closed agent desktop handle")
            self._agent_desktop = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_agent_active(self) -> bool:
        """``True`` if the agent desktop is currently the input desktop."""
        with self._lock:
            return self._agent_is_active

    @property
    def agent_desktop_handle(self):
        """The HDESK handle for the agent desktop, or None if not created."""
        with self._lock:
            return self._agent_desktop

    @property
    def agent_desktop_name(self) -> str:
        """The fixed name of the agent desktop."""
        return _AGENT_DESKTOP_NAME

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> DesktopManager:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.destroy()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _switch_to_user_unlocked(self) -> None:
        """Switch input back to the user's desktop (caller holds the lock)."""
        if not self._agent_is_active:
            log.debug("User desktop already active — no-op")
            return
        if self._user_desktop is None:
            raise DesktopError("User desktop handle is not available")
        if not user32.SwitchDesktop(self._user_desktop):
            raise DesktopError(
                f"SwitchDesktop(user) failed, error {ctypes.get_last_error()}"
            )
        self._agent_is_active = False
        log.info("Switched input back to user desktop")
