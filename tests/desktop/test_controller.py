"""Tests for DesktopController — mode transition orchestration."""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from windowspc_mcp.confinement.errors import InvalidStateError
from windowspc_mcp.desktop.capture import FrameBuffer
from windowspc_mcp.desktop.controller import DesktopController
from windowspc_mcp.desktop.gate import InputGate, InputMode
from windowspc_mcp.desktop.hotkeys import HotkeyId, HotkeyService
from windowspc_mcp.desktop.manager import DesktopManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def dm() -> MagicMock:
    """Mock DesktopManager."""
    mock = MagicMock(spec=DesktopManager)
    mock.is_agent_active = False
    mock.agent_desktop_handle = 42  # Fake HDESK handle
    return mock


@pytest.fixture()
def gate() -> InputGate:
    """Real InputGate (lightweight, no Win32 calls)."""
    return InputGate()


@pytest.fixture()
def hotkeys() -> MagicMock:
    """Mock HotkeyService."""
    return MagicMock(spec=HotkeyService)


@pytest.fixture()
def mock_capture():
    """Patch DesktopCapture so controller doesn't create real one."""
    with patch("windowspc_mcp.desktop.controller.DesktopCapture") as cls:
        instance = MagicMock()
        instance.frame_buffer = FrameBuffer(width=1920, height=1080)
        cls.return_value = instance
        yield cls


@pytest.fixture()
def mock_viewer():
    """Patch ViewerWindow so controller doesn't create real one."""
    with patch("windowspc_mcp.desktop.controller.ViewerWindow") as cls:
        cls.return_value = MagicMock()
        yield cls


@pytest.fixture()
def ctrl(
    dm: MagicMock, gate: InputGate, hotkeys: MagicMock,
    mock_capture, mock_viewer,
) -> DesktopController:
    """DesktopController wired with mocks (not started)."""
    return DesktopController(dm, gate, hotkeys)


@pytest.fixture()
def started_ctrl(
    dm: MagicMock, gate: InputGate, hotkeys: MagicMock,
    mock_capture, mock_viewer,
) -> DesktopController:
    """DesktopController already started in AGENT_SOLO mode."""
    c = DesktopController(dm, gate, hotkeys)
    c.start(InputMode.AGENT_SOLO)
    # Reset call history so tests only see calls made after start().
    dm.reset_mock()
    hotkeys.reset_mock()
    mock_capture.return_value.reset_mock()
    mock_viewer.return_value.reset_mock()
    return c


# ---------------------------------------------------------------------------
# start()
# ---------------------------------------------------------------------------


class TestStart:
    def test_start_creates_desktop_starts_hotkeys_sets_mode(
        self, ctrl: DesktopController, dm: MagicMock, gate: InputGate, hotkeys: MagicMock
    ) -> None:
        ctrl.start(InputMode.AGENT_SOLO)

        dm.create_agent_desktop.assert_called_once()
        hotkeys.start.assert_called_once()
        assert gate.mode is InputMode.AGENT_SOLO
        dm.switch_to_agent.assert_called_once()

    def test_start_with_human_home_does_not_switch_to_agent(
        self, ctrl: DesktopController, dm: MagicMock, gate: InputGate
    ) -> None:
        ctrl.start(InputMode.HUMAN_HOME)

        dm.create_agent_desktop.assert_called_once()
        dm.switch_to_agent.assert_not_called()
        assert gate.mode is InputMode.HUMAN_HOME

    def test_start_with_cowork_switches_to_agent(
        self, ctrl: DesktopController, dm: MagicMock, gate: InputGate
    ) -> None:
        ctrl.start(InputMode.COWORK)

        dm.switch_to_agent.assert_called_once()
        assert gate.mode is InputMode.COWORK

    def test_start_wires_hotkey_callbacks(
        self, ctrl: DesktopController, hotkeys: MagicMock
    ) -> None:
        ctrl.start()

        callbacks = hotkeys.start.call_args[0][0]
        assert set(callbacks.keys()) == {
            HotkeyId.TOGGLE,
            HotkeyId.OVERRIDE,
            HotkeyId.EMERGENCY,
        }

    def test_start_twice_raises(self, ctrl: DesktopController) -> None:
        ctrl.start()
        with pytest.raises(InvalidStateError, match="already started"):
            ctrl.start()


# ---------------------------------------------------------------------------
# stop()
# ---------------------------------------------------------------------------


class TestStop:
    def test_stop_shuts_down_cleanly(
        self, started_ctrl: DesktopController, dm: MagicMock, hotkeys: MagicMock
    ) -> None:
        started_ctrl.stop()

        hotkeys.stop.assert_called_once()
        dm.switch_to_user.assert_called_once()
        dm.destroy.assert_called_once()

    def test_stop_when_not_started_is_noop(
        self, ctrl: DesktopController, dm: MagicMock, hotkeys: MagicMock
    ) -> None:
        ctrl.stop()

        hotkeys.stop.assert_not_called()
        dm.switch_to_user.assert_not_called()
        dm.destroy.assert_not_called()

    def test_stop_idempotent(
        self, started_ctrl: DesktopController, dm: MagicMock
    ) -> None:
        started_ctrl.stop()
        dm.reset_mock()
        started_ctrl.stop()  # second stop should be a no-op
        dm.destroy.assert_not_called()


# ---------------------------------------------------------------------------
# toggle_mode
# ---------------------------------------------------------------------------


class TestToggleMode:
    def test_agent_solo_to_cowork(
        self, started_ctrl: DesktopController, gate: InputGate, dm: MagicMock
    ) -> None:
        assert gate.mode is InputMode.AGENT_SOLO

        started_ctrl.toggle_mode()

        assert gate.mode is InputMode.COWORK
        # COWORK stays on agent desktop.
        dm.switch_to_agent.assert_called_once()
        dm.switch_to_user.assert_not_called()

    def test_cowork_to_human_home(
        self, started_ctrl: DesktopController, gate: InputGate, dm: MagicMock
    ) -> None:
        gate.set_mode(InputMode.COWORK)

        started_ctrl.toggle_mode()

        assert gate.mode is InputMode.HUMAN_HOME
        dm.switch_to_user.assert_called_once()

    def test_human_home_to_agent_solo(
        self, started_ctrl: DesktopController, gate: InputGate, dm: MagicMock
    ) -> None:
        gate.set_mode(InputMode.HUMAN_HOME)

        started_ctrl.toggle_mode()

        assert gate.mode is InputMode.AGENT_SOLO
        dm.switch_to_agent.assert_called_once()

    def test_full_cycle(
        self, started_ctrl: DesktopController, gate: InputGate
    ) -> None:
        assert gate.mode is InputMode.AGENT_SOLO

        started_ctrl.toggle_mode()
        assert gate.mode is InputMode.COWORK

        started_ctrl.toggle_mode()
        assert gate.mode is InputMode.HUMAN_HOME

        started_ctrl.toggle_mode()
        assert gate.mode is InputMode.AGENT_SOLO

    def test_noop_in_human_override(
        self, started_ctrl: DesktopController, gate: InputGate, dm: MagicMock
    ) -> None:
        gate.set_mode(InputMode.HUMAN_OVERRIDE)

        started_ctrl.toggle_mode()

        assert gate.mode is InputMode.HUMAN_OVERRIDE
        dm.switch_to_agent.assert_not_called()
        dm.switch_to_user.assert_not_called()

    def test_noop_in_emergency_stop(
        self, started_ctrl: DesktopController, gate: InputGate, dm: MagicMock
    ) -> None:
        gate.set_mode(InputMode.EMERGENCY_STOP)

        started_ctrl.toggle_mode()

        assert gate.mode is InputMode.EMERGENCY_STOP
        dm.switch_to_agent.assert_not_called()
        dm.switch_to_user.assert_not_called()


# ---------------------------------------------------------------------------
# override
# ---------------------------------------------------------------------------


class TestOverride:
    def test_override_from_agent_solo(
        self, started_ctrl: DesktopController, gate: InputGate, dm: MagicMock
    ) -> None:
        assert gate.mode is InputMode.AGENT_SOLO

        started_ctrl.override()

        assert gate.mode is InputMode.HUMAN_OVERRIDE
        dm.switch_to_user.assert_called_once()

    def test_override_from_cowork(
        self, started_ctrl: DesktopController, gate: InputGate, dm: MagicMock
    ) -> None:
        gate.set_mode(InputMode.COWORK)

        started_ctrl.override()

        assert gate.mode is InputMode.HUMAN_OVERRIDE
        dm.switch_to_user.assert_called_once()

    def test_override_from_human_home(
        self, started_ctrl: DesktopController, gate: InputGate, dm: MagicMock
    ) -> None:
        gate.set_mode(InputMode.HUMAN_HOME)

        started_ctrl.override()

        assert gate.mode is InputMode.HUMAN_OVERRIDE
        # Was already on user desktop, should not call switch_to_user.
        dm.switch_to_user.assert_not_called()

    def test_override_noop_if_already_override(
        self, started_ctrl: DesktopController, gate: InputGate, dm: MagicMock
    ) -> None:
        started_ctrl.override()
        dm.reset_mock()

        started_ctrl.override()  # second override should be no-op

        dm.switch_to_user.assert_not_called()

    def test_override_noop_in_emergency_stop(
        self, started_ctrl: DesktopController, gate: InputGate, dm: MagicMock
    ) -> None:
        gate.set_mode(InputMode.EMERGENCY_STOP)

        started_ctrl.override()

        assert gate.mode is InputMode.EMERGENCY_STOP
        dm.switch_to_user.assert_not_called()


# ---------------------------------------------------------------------------
# resume_from_override
# ---------------------------------------------------------------------------


class TestResumeFromOverride:
    def test_resume_restores_agent_solo(
        self, started_ctrl: DesktopController, gate: InputGate, dm: MagicMock
    ) -> None:
        assert gate.mode is InputMode.AGENT_SOLO
        started_ctrl.override()
        dm.reset_mock()

        started_ctrl.resume_from_override()

        assert gate.mode is InputMode.AGENT_SOLO
        dm.switch_to_agent.assert_called_once()

    def test_resume_restores_cowork(
        self, started_ctrl: DesktopController, gate: InputGate, dm: MagicMock
    ) -> None:
        gate.set_mode(InputMode.COWORK)
        started_ctrl.override()
        dm.reset_mock()

        started_ctrl.resume_from_override()

        assert gate.mode is InputMode.COWORK
        dm.switch_to_agent.assert_called_once()

    def test_resume_restores_human_home(
        self, started_ctrl: DesktopController, gate: InputGate, dm: MagicMock
    ) -> None:
        gate.set_mode(InputMode.HUMAN_HOME)
        started_ctrl.override()
        dm.reset_mock()

        started_ctrl.resume_from_override()

        assert gate.mode is InputMode.HUMAN_HOME
        # HUMAN_HOME is on user desktop, no switch to agent.
        dm.switch_to_agent.assert_not_called()

    def test_resume_raises_if_not_in_override(
        self, started_ctrl: DesktopController, gate: InputGate
    ) -> None:
        assert gate.mode is InputMode.AGENT_SOLO

        with pytest.raises(InvalidStateError, match="HUMAN_OVERRIDE"):
            started_ctrl.resume_from_override()

    def test_resume_raises_in_emergency_stop(
        self, started_ctrl: DesktopController, gate: InputGate
    ) -> None:
        gate.set_mode(InputMode.EMERGENCY_STOP)

        with pytest.raises(InvalidStateError, match="HUMAN_OVERRIDE"):
            started_ctrl.resume_from_override()


# ---------------------------------------------------------------------------
# emergency_stop
# ---------------------------------------------------------------------------


class TestEmergencyStop:
    def test_emergency_stop_from_agent_solo(
        self, started_ctrl: DesktopController, gate: InputGate, dm: MagicMock, hotkeys: MagicMock
    ) -> None:
        started_ctrl.emergency_stop()

        assert gate.mode is InputMode.EMERGENCY_STOP
        dm.switch_to_user.assert_called_once()
        dm.destroy.assert_called_once()
        hotkeys.stop.assert_called_once()

    def test_emergency_stop_from_cowork(
        self, started_ctrl: DesktopController, gate: InputGate, dm: MagicMock, hotkeys: MagicMock
    ) -> None:
        gate.set_mode(InputMode.COWORK)

        started_ctrl.emergency_stop()

        assert gate.mode is InputMode.EMERGENCY_STOP
        dm.switch_to_user.assert_called_once()
        dm.destroy.assert_called_once()
        hotkeys.stop.assert_called_once()

    def test_emergency_stop_from_human_override(
        self, started_ctrl: DesktopController, gate: InputGate, dm: MagicMock, hotkeys: MagicMock
    ) -> None:
        started_ctrl.override()
        dm.reset_mock()
        hotkeys.reset_mock()

        started_ctrl.emergency_stop()

        assert gate.mode is InputMode.EMERGENCY_STOP
        dm.switch_to_user.assert_called_once()
        dm.destroy.assert_called_once()
        hotkeys.stop.assert_called_once()

    def test_emergency_stop_idempotent(
        self, started_ctrl: DesktopController, dm: MagicMock
    ) -> None:
        started_ctrl.emergency_stop()
        dm.reset_mock()

        started_ctrl.emergency_stop()  # second call should be a no-op

        dm.switch_to_user.assert_not_called()
        dm.destroy.assert_not_called()

    def test_emergency_stop_is_terminal(
        self, started_ctrl: DesktopController, gate: InputGate
    ) -> None:
        started_ctrl.emergency_stop()

        # toggle_mode should be no-op
        started_ctrl.toggle_mode()
        assert gate.mode is InputMode.EMERGENCY_STOP

        # override should be no-op
        started_ctrl.override()
        assert gate.mode is InputMode.EMERGENCY_STOP


# ---------------------------------------------------------------------------
# mode property
# ---------------------------------------------------------------------------


class TestModeProperty:
    def test_mode_delegates_to_gate(
        self, started_ctrl: DesktopController, gate: InputGate
    ) -> None:
        assert started_ctrl.mode is gate.mode

        gate.set_mode(InputMode.COWORK)
        assert started_ctrl.mode is InputMode.COWORK


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


class TestContextManager:
    def test_enter_starts_exit_stops(
        self, dm: MagicMock, gate: InputGate, hotkeys: MagicMock
    ) -> None:
        ctrl = DesktopController(dm, gate, hotkeys)

        with ctrl:
            dm.create_agent_desktop.assert_called_once()
            hotkeys.start.assert_called_once()
            assert gate.mode is InputMode.AGENT_SOLO

        hotkeys.stop.assert_called_once()
        dm.destroy.assert_called_once()

    def test_exit_on_exception(
        self, dm: MagicMock, gate: InputGate, hotkeys: MagicMock
    ) -> None:
        ctrl = DesktopController(dm, gate, hotkeys)

        with pytest.raises(RuntimeError):
            with ctrl:
                raise RuntimeError("boom")

        # Should still clean up.
        hotkeys.stop.assert_called_once()
        dm.destroy.assert_called_once()


# ---------------------------------------------------------------------------
# Viewer integration
# ---------------------------------------------------------------------------


class TestViewerIntegration:
    def test_start_creates_capture_and_viewer(
        self, ctrl: DesktopController, dm: MagicMock, mock_capture, mock_viewer
    ) -> None:
        ctrl.start(InputMode.AGENT_SOLO)

        mock_capture.assert_called_once()
        capture_kwargs = mock_capture.call_args
        assert capture_kwargs[1]["desktop_handle"] == 42
        assert capture_kwargs[1]["width"] == 1920
        assert capture_kwargs[1]["height"] == 1080
        mock_capture.return_value.start.assert_called_once()

        mock_viewer.assert_called_once()
        mock_viewer.return_value.start.assert_called_once()

    def test_stop_stops_viewer_and_capture(
        self, started_ctrl: DesktopController, mock_capture, mock_viewer
    ) -> None:
        started_ctrl.stop()

        mock_viewer.return_value.stop.assert_called_once()
        mock_capture.return_value.stop.assert_called_once()

    def test_emergency_stop_stops_viewer(
        self, started_ctrl: DesktopController, mock_capture, mock_viewer
    ) -> None:
        started_ctrl.emergency_stop()

        mock_viewer.return_value.stop.assert_called_once()
        mock_capture.return_value.stop.assert_called_once()

    def test_viewer_receives_capture_frame_buffer(
        self, ctrl: DesktopController, mock_capture, mock_viewer
    ) -> None:
        ctrl.start(InputMode.AGENT_SOLO)

        viewer_call = mock_viewer.call_args
        assert viewer_call[1]["frame_buffer"] is mock_capture.return_value.frame_buffer
