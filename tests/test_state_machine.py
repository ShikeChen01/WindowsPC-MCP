import pytest
from windowsmcp_custom.server import ServerStateManager, ServerState


class TestServerStateManager:
    def test_initial_state(self):
        mgr = ServerStateManager()
        assert mgr.state == ServerState.INIT

    def test_transition(self):
        mgr = ServerStateManager()
        mgr.transition(ServerState.READY)
        assert mgr.state == ServerState.READY

    def test_gui_available_when_ready(self):
        mgr = ServerStateManager()
        mgr.transition(ServerState.READY)
        assert mgr.is_gui_available
        assert mgr.is_gui_write_available

    def test_gui_read_only_when_degraded(self):
        mgr = ServerStateManager()
        mgr.transition(ServerState.DEGRADED, "test reason")
        assert mgr.is_gui_available
        assert not mgr.is_gui_write_available

    def test_no_gui_when_driver_missing(self):
        mgr = ServerStateManager()
        mgr.transition(ServerState.DRIVER_MISSING)
        assert not mgr.is_gui_available

    def test_unconfined_available_except_init_shutdown(self):
        mgr = ServerStateManager()
        assert not mgr.is_unconfined_available  # INIT
        mgr.transition(ServerState.DRIVER_MISSING)
        assert mgr.is_unconfined_available
        mgr.transition(ServerState.SHUTTING_DOWN)
        assert not mgr.is_unconfined_available

    def test_listener_called(self):
        mgr = ServerStateManager()
        events = []
        mgr.add_listener(lambda old, new, reason: events.append((old, new, reason)))
        mgr.transition(ServerState.READY)
        assert len(events) == 1
        assert events[0] == (ServerState.INIT, ServerState.READY, None)

    def test_get_status(self):
        mgr = ServerStateManager()
        mgr.transition(ServerState.READY)
        status = mgr.get_status()
        assert status["state"] == "ready"
        assert status["gui_available"] is True
