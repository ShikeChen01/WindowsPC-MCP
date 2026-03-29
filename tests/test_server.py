"""Tests for server – ServerStateManager and ServerState enum."""

import threading
from unittest.mock import MagicMock, call

import pytest

from windowspc_mcp.server import ServerState, ServerStateManager


# ---------------------------------------------------------------------------
# ServerState enum
# ---------------------------------------------------------------------------

class TestServerStateEnum:
    """ServerState has exactly 8 members with expected string values."""

    def test_all_members(self):
        members = list(ServerState)
        assert len(members) == 8

    @pytest.mark.parametrize(
        "member, value",
        [
            (ServerState.INIT, "init"),
            (ServerState.DRIVER_MISSING, "driver_missing"),
            (ServerState.CREATING_DISPLAY, "creating_display"),
            (ServerState.CREATE_FAILED, "create_failed"),
            (ServerState.READY, "ready"),
            (ServerState.DEGRADED, "degraded"),
            (ServerState.RECOVERING, "recovering"),
            (ServerState.SHUTTING_DOWN, "shutting_down"),
        ],
    )
    def test_enum_value(self, member, value):
        assert member.value == value


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

class TestInitialState:
    """ServerStateManager starts in INIT with no degraded reason."""

    def test_initial_state_is_init(self):
        mgr = ServerStateManager()
        assert mgr.state == ServerState.INIT

    def test_initial_degraded_reason_is_none(self):
        mgr = ServerStateManager()
        assert mgr.get_status()["degraded_reason"] is None

    def test_no_listeners_initially(self):
        mgr = ServerStateManager()
        assert mgr._state_listeners == []


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------

class TestTransition:
    """transition() updates state, stores reason, and notifies listeners."""

    def test_simple_transition(self):
        mgr = ServerStateManager()
        mgr.transition(ServerState.READY)
        assert mgr.state == ServerState.READY

    def test_transition_returns_none(self):
        mgr = ServerStateManager()
        result = mgr.transition(ServerState.READY)
        assert result is None

    @pytest.mark.parametrize("target", list(ServerState))
    def test_transition_to_every_state(self, target):
        mgr = ServerStateManager()
        mgr.transition(target)
        assert mgr.state == target

    def test_transition_chain(self):
        mgr = ServerStateManager()
        mgr.transition(ServerState.CREATING_DISPLAY)
        mgr.transition(ServerState.READY)
        mgr.transition(ServerState.DEGRADED, "flicker")
        mgr.transition(ServerState.RECOVERING)
        mgr.transition(ServerState.READY)
        mgr.transition(ServerState.SHUTTING_DOWN)
        assert mgr.state == ServerState.SHUTTING_DOWN

    def test_self_transition(self):
        mgr = ServerStateManager()
        mgr.transition(ServerState.INIT)
        assert mgr.state == ServerState.INIT


# ---------------------------------------------------------------------------
# Degraded reason
# ---------------------------------------------------------------------------

class TestDegradedReason:
    """degraded_reason is set only for DEGRADED state and cleared otherwise."""

    def test_set_on_degraded(self):
        mgr = ServerStateManager()
        mgr.transition(ServerState.DEGRADED, "capture lost")
        assert mgr.get_status()["degraded_reason"] == "capture lost"

    def test_cleared_on_non_degraded(self):
        mgr = ServerStateManager()
        mgr.transition(ServerState.DEGRADED, "err")
        mgr.transition(ServerState.READY)
        assert mgr.get_status()["degraded_reason"] is None

    def test_updated_on_repeated_degraded(self):
        mgr = ServerStateManager()
        mgr.transition(ServerState.DEGRADED, "reason1")
        mgr.transition(ServerState.DEGRADED, "reason2")
        assert mgr.get_status()["degraded_reason"] == "reason2"

    def test_degraded_without_reason(self):
        mgr = ServerStateManager()
        mgr.transition(ServerState.DEGRADED)
        assert mgr.get_status()["degraded_reason"] is None

    def test_reason_ignored_for_non_degraded(self):
        mgr = ServerStateManager()
        mgr.transition(ServerState.READY, "should be ignored")
        assert mgr.get_status()["degraded_reason"] is None

    @pytest.mark.parametrize(
        "clear_target",
        [s for s in ServerState if s != ServerState.DEGRADED],
    )
    def test_cleared_on_transition_to_each_non_degraded(self, clear_target):
        mgr = ServerStateManager()
        mgr.transition(ServerState.DEGRADED, "will be cleared")
        mgr.transition(clear_target)
        assert mgr.get_status()["degraded_reason"] is None


# ---------------------------------------------------------------------------
# is_gui_available – all 8 states
# ---------------------------------------------------------------------------

class TestIsGuiAvailable:
    """is_gui_available is True only for READY and DEGRADED."""

    @pytest.mark.parametrize(
        "state, expected",
        [
            (ServerState.INIT, False),
            (ServerState.DRIVER_MISSING, False),
            (ServerState.CREATING_DISPLAY, False),
            (ServerState.CREATE_FAILED, False),
            (ServerState.READY, True),
            (ServerState.DEGRADED, True),
            (ServerState.RECOVERING, False),
            (ServerState.SHUTTING_DOWN, False),
        ],
    )
    def test_is_gui_available(self, state, expected):
        mgr = ServerStateManager()
        mgr.transition(state)
        assert mgr.is_gui_available is expected


# ---------------------------------------------------------------------------
# is_gui_write_available – all 8 states
# ---------------------------------------------------------------------------

class TestIsGuiWriteAvailable:
    """is_gui_write_available is True only for READY."""

    @pytest.mark.parametrize(
        "state, expected",
        [
            (ServerState.INIT, False),
            (ServerState.DRIVER_MISSING, False),
            (ServerState.CREATING_DISPLAY, False),
            (ServerState.CREATE_FAILED, False),
            (ServerState.READY, True),
            (ServerState.DEGRADED, False),
            (ServerState.RECOVERING, False),
            (ServerState.SHUTTING_DOWN, False),
        ],
    )
    def test_is_gui_write_available(self, state, expected):
        mgr = ServerStateManager()
        mgr.transition(state)
        assert mgr.is_gui_write_available is expected


# ---------------------------------------------------------------------------
# is_unconfined_available – all 8 states
# ---------------------------------------------------------------------------

class TestIsUnconfinedAvailable:
    """is_unconfined_available is False only for INIT and SHUTTING_DOWN."""

    @pytest.mark.parametrize(
        "state, expected",
        [
            (ServerState.INIT, False),
            (ServerState.DRIVER_MISSING, True),
            (ServerState.CREATING_DISPLAY, True),
            (ServerState.CREATE_FAILED, True),
            (ServerState.READY, True),
            (ServerState.DEGRADED, True),
            (ServerState.RECOVERING, True),
            (ServerState.SHUTTING_DOWN, False),
        ],
    )
    def test_is_unconfined_available(self, state, expected):
        mgr = ServerStateManager()
        mgr.transition(state)
        assert mgr.is_unconfined_available is expected


# ---------------------------------------------------------------------------
# get_status
# ---------------------------------------------------------------------------

class TestGetStatus:
    """get_status() returns a dict with expected keys and values."""

    def test_keys_present(self):
        mgr = ServerStateManager()
        status = mgr.get_status()
        assert set(status.keys()) == {
            "state",
            "gui_available",
            "gui_write_available",
            "degraded_reason",
        }

    def test_init_status(self):
        mgr = ServerStateManager()
        status = mgr.get_status()
        assert status["state"] == "init"
        assert status["gui_available"] is False
        assert status["gui_write_available"] is False
        assert status["degraded_reason"] is None

    def test_ready_status(self):
        mgr = ServerStateManager()
        mgr.transition(ServerState.READY)
        status = mgr.get_status()
        assert status["state"] == "ready"
        assert status["gui_available"] is True
        assert status["gui_write_available"] is True
        assert status["degraded_reason"] is None

    def test_degraded_status_with_reason(self):
        mgr = ServerStateManager()
        mgr.transition(ServerState.DEGRADED, "screen lost")
        status = mgr.get_status()
        assert status["state"] == "degraded"
        assert status["gui_available"] is True
        assert status["gui_write_available"] is False
        assert status["degraded_reason"] == "screen lost"

    def test_degraded_status_without_reason(self):
        mgr = ServerStateManager()
        mgr.transition(ServerState.DEGRADED)
        status = mgr.get_status()
        assert status["degraded_reason"] is None

    @pytest.mark.parametrize("state", list(ServerState))
    def test_state_value_matches_enum(self, state):
        mgr = ServerStateManager()
        mgr.transition(state)
        assert mgr.get_status()["state"] == state.value


# ---------------------------------------------------------------------------
# Listeners – ordering and arguments
# ---------------------------------------------------------------------------

class TestListeners:
    """Listeners are called in registration order with correct args."""

    def test_single_listener_called(self):
        mgr = ServerStateManager()
        cb = MagicMock()
        mgr.add_listener(cb)
        mgr.transition(ServerState.READY)
        cb.assert_called_once_with(ServerState.INIT, ServerState.READY, None)

    def test_listener_receives_reason(self):
        mgr = ServerStateManager()
        cb = MagicMock()
        mgr.add_listener(cb)
        mgr.transition(ServerState.DEGRADED, "oops")
        cb.assert_called_once_with(ServerState.INIT, ServerState.DEGRADED, "oops")

    def test_multiple_listeners_called_in_order(self):
        mgr = ServerStateManager()
        order = []
        mgr.add_listener(lambda o, n, r: order.append("A"))
        mgr.add_listener(lambda o, n, r: order.append("B"))
        mgr.add_listener(lambda o, n, r: order.append("C"))
        mgr.transition(ServerState.READY)
        assert order == ["A", "B", "C"]

    def test_all_listeners_receive_same_args(self):
        mgr = ServerStateManager()
        cb1 = MagicMock()
        cb2 = MagicMock()
        mgr.add_listener(cb1)
        mgr.add_listener(cb2)
        mgr.transition(ServerState.DEGRADED, "err")
        expected = call(ServerState.INIT, ServerState.DEGRADED, "err")
        assert cb1.call_args == expected
        assert cb2.call_args == expected

    def test_listener_across_multiple_transitions(self):
        mgr = ServerStateManager()
        cb = MagicMock()
        mgr.add_listener(cb)
        mgr.transition(ServerState.CREATING_DISPLAY)
        mgr.transition(ServerState.READY)
        mgr.transition(ServerState.SHUTTING_DOWN)

        assert cb.call_count == 3
        assert cb.call_args_list == [
            call(ServerState.INIT, ServerState.CREATING_DISPLAY, None),
            call(ServerState.CREATING_DISPLAY, ServerState.READY, None),
            call(ServerState.READY, ServerState.SHUTTING_DOWN, None),
        ]

    def test_listener_added_after_transition_sees_only_subsequent(self):
        mgr = ServerStateManager()
        mgr.transition(ServerState.CREATING_DISPLAY)
        cb = MagicMock()
        mgr.add_listener(cb)
        mgr.transition(ServerState.READY)
        cb.assert_called_once_with(
            ServerState.CREATING_DISPLAY, ServerState.READY, None
        )

    def test_no_listeners_no_error(self):
        mgr = ServerStateManager()
        mgr.transition(ServerState.READY)  # must not raise

    def test_listener_with_self_transition(self):
        mgr = ServerStateManager()
        cb = MagicMock()
        mgr.add_listener(cb)
        mgr.transition(ServerState.INIT)
        cb.assert_called_once_with(ServerState.INIT, ServerState.INIT, None)


# ---------------------------------------------------------------------------
# Thread safety (basic check)
# ---------------------------------------------------------------------------

class TestThreadSafety:
    """Manager uses an RLock so concurrent transitions should not corrupt state."""

    def test_concurrent_transitions(self):
        mgr = ServerStateManager()
        events = []
        mgr.add_listener(lambda o, n, r: events.append(n))

        states = [
            ServerState.CREATING_DISPLAY,
            ServerState.READY,
            ServerState.DEGRADED,
            ServerState.RECOVERING,
            ServerState.READY,
        ]

        threads = [
            threading.Thread(target=mgr.transition, args=(s,)) for s in states
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All transitions fired
        assert len(events) == len(states)
        # Final state is one of the target states
        assert mgr.state in states
