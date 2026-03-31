"""Tests for windowspc_mcp.desktop.manager — DesktopManager class."""

from __future__ import annotations

import subprocess
import threading
from unittest.mock import MagicMock, patch

import pytest

# We must mock the Win32 bindings before importing the module, since the
# module-level code configures argtypes/restype on ctypes.windll.  We patch
# at the already-imported module-level references that DesktopManager uses.

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Fake handle values
_USER_HDESK = 0xAAAA
_AGENT_HDESK = 0xBBBB
_THREAD_ID = 1234


@pytest.fixture()
def _win32(monkeypatch):
    """Patch all Win32 functions used by the manager module.

    Yields a namespace object whose attributes are the mock callables so tests
    can inspect calls and override return values.
    """
    import windowspc_mcp.desktop.manager as mod

    mocks = type("Win32Mocks", (), {})()

    # -- kernel32 --
    mock_kernel32 = MagicMock()
    mock_kernel32.GetCurrentThreadId.return_value = _THREAD_ID
    mock_kernel32.GetLastError.return_value = 0
    monkeypatch.setattr(mod, "kernel32", mock_kernel32)
    mocks.kernel32 = mock_kernel32

    # -- user32 --
    mock_user32 = MagicMock()
    mock_user32.GetThreadDesktop.return_value = _USER_HDESK
    mock_user32.CreateDesktopW.return_value = _AGENT_HDESK
    mock_user32.SwitchDesktop.return_value = True
    mock_user32.CloseDesktop.return_value = True
    mock_user32.OpenInputDesktop.return_value = _USER_HDESK
    mock_user32.SetThreadDesktop.return_value = True
    monkeypatch.setattr(mod, "user32", mock_user32)
    mocks.user32 = mock_user32

    return mocks


@pytest.fixture()
def manager(_win32):
    """Return a fresh DesktopManager with mocked Win32 layer."""
    from windowspc_mcp.desktop.manager import DesktopManager

    return DesktopManager()


@pytest.fixture()
def win32(_win32):
    return _win32


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestInit:
    def test_captures_user_desktop(self, manager, win32):
        """Init should call GetThreadDesktop to capture the user handle."""
        win32.kernel32.GetCurrentThreadId.assert_called()
        win32.user32.GetThreadDesktop.assert_called_with(_THREAD_ID)

    def test_agent_desktop_not_created_yet(self, manager):
        assert manager._agent_desktop is None
        assert not manager.is_agent_active

    def test_get_thread_desktop_failure(self, _win32):
        """If GetThreadDesktop returns NULL, raise DesktopError."""
        from windowspc_mcp.desktop.manager import DesktopError, DesktopManager

        _win32.user32.GetThreadDesktop.return_value = 0
        with pytest.raises(DesktopError, match="GetThreadDesktop failed"):
            DesktopManager()


# ---------------------------------------------------------------------------
# Desktop creation
# ---------------------------------------------------------------------------


class TestCreateAgentDesktop:
    def test_happy_path(self, manager, win32):
        manager.create_agent_desktop()
        win32.user32.CreateDesktopW.assert_called_once()
        call_args = win32.user32.CreateDesktopW.call_args
        assert call_args[0][0] == "WindowsPC_MCP_Agent"
        assert manager._agent_desktop == _AGENT_HDESK

    def test_already_exists_raises(self, manager):
        manager.create_agent_desktop()
        from windowspc_mcp.confinement.errors import InvalidStateError

        with pytest.raises(InvalidStateError, match="already exists"):
            manager.create_agent_desktop()

    def test_create_fails_returns_null(self, manager, win32):
        from windowspc_mcp.desktop.manager import DesktopError

        win32.user32.CreateDesktopW.return_value = 0
        win32.kernel32.GetLastError.return_value = 5  # ACCESS_DENIED
        with pytest.raises(DesktopError, match="CreateDesktopW failed"):
            manager.create_agent_desktop()

    def test_agent_desktop_name_property(self, manager):
        assert manager.agent_desktop_name == "WindowsPC_MCP_Agent"


# ---------------------------------------------------------------------------
# Switching
# ---------------------------------------------------------------------------


class TestSwitchToAgent:
    def test_switch_to_agent(self, manager, win32):
        manager.create_agent_desktop()
        manager.switch_to_agent()
        win32.user32.SwitchDesktop.assert_called_with(_AGENT_HDESK)
        assert manager.is_agent_active

    def test_switch_to_agent_no_desktop_raises(self, manager):
        from windowspc_mcp.confinement.errors import InvalidStateError

        with pytest.raises(InvalidStateError, match="not been created"):
            manager.switch_to_agent()

    def test_switch_to_agent_already_active_is_noop(self, manager, win32):
        manager.create_agent_desktop()
        manager.switch_to_agent()
        win32.user32.SwitchDesktop.reset_mock()
        # second call should be a no-op
        manager.switch_to_agent()
        win32.user32.SwitchDesktop.assert_not_called()

    def test_switch_to_agent_fails(self, manager, win32):
        from windowspc_mcp.desktop.manager import DesktopError

        manager.create_agent_desktop()
        win32.user32.SwitchDesktop.return_value = False
        win32.kernel32.GetLastError.return_value = 5
        with pytest.raises(DesktopError, match="SwitchDesktop.*failed"):
            manager.switch_to_agent()


class TestSwitchToUser:
    def test_switch_to_user(self, manager, win32):
        manager.create_agent_desktop()
        manager.switch_to_agent()
        win32.user32.SwitchDesktop.reset_mock()
        manager.switch_to_user()
        win32.user32.SwitchDesktop.assert_called_with(_USER_HDESK)
        assert not manager.is_agent_active

    def test_switch_to_user_already_on_user_is_noop(self, manager, win32):
        """If user desktop is already active, switch_to_user is a no-op."""
        manager.switch_to_user()
        win32.user32.SwitchDesktop.assert_not_called()

    def test_switch_to_user_fails(self, manager, win32):
        from windowspc_mcp.desktop.manager import DesktopError

        manager.create_agent_desktop()
        manager.switch_to_agent()
        # Now make SwitchDesktop fail when switching back
        win32.user32.SwitchDesktop.return_value = False
        win32.kernel32.GetLastError.return_value = 5
        with pytest.raises(DesktopError, match="SwitchDesktop.*failed"):
            manager.switch_to_user()


# ---------------------------------------------------------------------------
# Destroy
# ---------------------------------------------------------------------------


class TestDestroy:
    def test_destroy_closes_handle(self, manager, win32):
        manager.create_agent_desktop()
        manager.destroy()
        win32.user32.CloseDesktop.assert_called_with(_AGENT_HDESK)
        assert manager._agent_desktop is None

    def test_destroy_switches_back_if_agent_active(self, manager, win32):
        manager.create_agent_desktop()
        manager.switch_to_agent()
        win32.user32.SwitchDesktop.reset_mock()

        manager.destroy()

        # Should have switched back to user first
        calls = win32.user32.SwitchDesktop.call_args_list
        assert len(calls) == 1
        assert calls[0][0][0] == _USER_HDESK
        assert not manager.is_agent_active
        assert manager._agent_desktop is None

    def test_destroy_noop_when_no_desktop(self, manager, win32):
        """Destroy without create should be a harmless no-op."""
        manager.destroy()
        win32.user32.CloseDesktop.assert_not_called()

    def test_destroy_twice_is_safe(self, manager, win32):
        manager.create_agent_desktop()
        manager.destroy()
        manager.destroy()  # second call is no-op
        assert win32.user32.CloseDesktop.call_count == 1


# ---------------------------------------------------------------------------
# launch_on_agent
# ---------------------------------------------------------------------------


class TestLaunchOnAgent:
    def test_launch_sets_lp_desktop(self, manager, win32):
        manager.create_agent_desktop()

        with patch("windowspc_mcp.desktop.manager.subprocess") as mock_sub:
            mock_proc = MagicMock()
            mock_proc.pid = 42
            mock_sub.Popen.return_value = mock_proc
            mock_sub.STARTUPINFO.return_value = MagicMock()

            pid = manager.launch_on_agent("notepad.exe", args=["test.txt"], cwd="C:\\tmp")

            assert pid == 42
            mock_sub.Popen.assert_called_once()
            call_kwargs = mock_sub.Popen.call_args
            si = call_kwargs.kwargs.get("startupinfo") or call_kwargs[1].get("startupinfo")
            assert si.lpDesktop == "WindowsPC_MCP_Agent"
            cmd = call_kwargs[0][0] if call_kwargs[0] else call_kwargs.kwargs["cmd"]
            assert cmd == ["notepad.exe", "test.txt"]

    def test_launch_no_args_no_cwd(self, manager, win32):
        manager.create_agent_desktop()

        with patch("windowspc_mcp.desktop.manager.subprocess") as mock_sub:
            mock_proc = MagicMock()
            mock_proc.pid = 99
            mock_sub.Popen.return_value = mock_proc
            mock_sub.STARTUPINFO.return_value = MagicMock()

            pid = manager.launch_on_agent("calc.exe")
            assert pid == 99
            call_args = mock_sub.Popen.call_args
            assert call_args[0][0] == ["calc.exe"]

    def test_launch_without_agent_desktop_raises(self, manager):
        from windowspc_mcp.confinement.errors import InvalidStateError

        with pytest.raises(InvalidStateError, match="not been created"):
            manager.launch_on_agent("notepad.exe")


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


class TestThreadSafety:
    def test_concurrent_switch_does_not_corrupt_state(self, manager, win32):
        """Hammer switch_to_agent / switch_to_user from many threads."""
        manager.create_agent_desktop()
        errors: list[Exception] = []
        barrier = threading.Barrier(20)

        def toggle(i: int) -> None:
            try:
                barrier.wait(timeout=5)
                if i % 2 == 0:
                    manager.switch_to_agent()
                else:
                    manager.switch_to_user()
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=toggle, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        # No exceptions should have escaped (some switch_to_user may be no-ops).
        assert errors == [], f"Thread errors: {errors}"

    def test_concurrent_create_only_one_wins(self, manager, win32):
        """If multiple threads try to create, only one should succeed."""
        results: list[str] = []
        barrier = threading.Barrier(5)

        def try_create() -> None:
            barrier.wait(timeout=5)
            try:
                manager.create_agent_desktop()
                results.append("ok")
            except Exception:
                results.append("fail")

        threads = [threading.Thread(target=try_create) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert results.count("ok") == 1
        assert results.count("fail") == 4


# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


class TestErrorHierarchy:
    def test_desktop_error_is_windowsmcp_error(self):
        from windowspc_mcp.confinement.errors import WindowsMCPError
        from windowspc_mcp.desktop.manager import DesktopError

        assert issubclass(DesktopError, WindowsMCPError)

    def test_desktop_error_message(self):
        from windowspc_mcp.desktop.manager import DesktopError

        err = DesktopError("test message")
        assert str(err) == "test message"
