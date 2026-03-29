"""Tests for ipc.commands – CommandReceiver."""

from windowspc_mcp.ipc.commands import CommandReceiver


class TestCommandReceiverInit:
    """CommandReceiver can be constructed."""

    def test_instantiation(self):
        receiver = CommandReceiver()
        assert receiver is not None

    def test_multiple_instances_independent(self):
        a = CommandReceiver()
        b = CommandReceiver()
        assert a is not b


class TestCommandReceiverStart:
    """start() is callable and idempotent."""

    def test_start_returns_none(self):
        receiver = CommandReceiver()
        result = receiver.start()
        assert result is None

    def test_start_idempotent(self):
        receiver = CommandReceiver()
        receiver.start()
        receiver.start()  # second call must not raise


class TestCommandReceiverStop:
    """stop() is callable and idempotent."""

    def test_stop_returns_none(self):
        receiver = CommandReceiver()
        result = receiver.stop()
        assert result is None

    def test_stop_without_start(self):
        receiver = CommandReceiver()
        receiver.stop()  # must not raise

    def test_stop_idempotent(self):
        receiver = CommandReceiver()
        receiver.start()
        receiver.stop()
        receiver.stop()  # second call must not raise


class TestCommandReceiverLifecycle:
    """Full start/stop lifecycle."""

    def test_start_then_stop(self):
        receiver = CommandReceiver()
        receiver.start()
        receiver.stop()

    def test_restart(self):
        receiver = CommandReceiver()
        receiver.start()
        receiver.stop()
        receiver.start()
        receiver.stop()
