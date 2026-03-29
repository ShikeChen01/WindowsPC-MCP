"""Tests for ipc.status – StatusPublisher."""

import json
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from windowspc_mcp.ipc.status import StatusPublisher, STATUS_FILE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_status():
    """Return a simple status dict for testing."""
    return {"state": "ready", "gui_available": True}


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestStatusPublisherInit:
    """StatusPublisher stores the callable and starts in stopped state."""

    def test_stores_get_status_callable(self):
        fn = MagicMock(return_value={})
        sp = StatusPublisher(fn)
        assert sp._get_status is fn

    def test_starts_not_running(self):
        sp = StatusPublisher(lambda: {})
        assert sp._running is False

    def test_thread_is_none_initially(self):
        sp = StatusPublisher(lambda: {})
        assert sp._thread is None


# ---------------------------------------------------------------------------
# start()
# ---------------------------------------------------------------------------

class TestStatusPublisherStart:
    """start() creates the status directory, sets _running, and spawns a thread."""

    @patch.object(Path, "mkdir")
    @patch("threading.Thread")
    def test_start_creates_directory(self, mock_thread_cls, mock_mkdir):
        mock_thread = MagicMock()
        mock_thread_cls.return_value = mock_thread

        sp = StatusPublisher(lambda: {})
        sp.start()

        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)

    @patch.object(Path, "mkdir")
    @patch("threading.Thread")
    def test_start_sets_running_true(self, mock_thread_cls, mock_mkdir):
        mock_thread = MagicMock()
        mock_thread_cls.return_value = mock_thread

        sp = StatusPublisher(lambda: {})
        sp.start()

        assert sp._running is True

    @patch.object(Path, "mkdir")
    @patch("threading.Thread")
    def test_start_spawns_daemon_thread(self, mock_thread_cls, mock_mkdir):
        mock_thread = MagicMock()
        mock_thread_cls.return_value = mock_thread

        sp = StatusPublisher(lambda: {})
        sp.start()

        mock_thread_cls.assert_called_once_with(target=sp._publish_loop, daemon=True)
        mock_thread.start.assert_called_once()


# ---------------------------------------------------------------------------
# stop()
# ---------------------------------------------------------------------------

class TestStatusPublisherStop:
    """stop() clears _running, joins thread, and removes the status file."""

    def test_stop_clears_running(self):
        sp = StatusPublisher(lambda: {})
        sp._running = True
        sp._thread = None
        with patch.object(Path, "exists", return_value=False):
            sp.stop()
        assert sp._running is False

    def test_stop_joins_thread_with_timeout(self):
        sp = StatusPublisher(lambda: {})
        sp._running = True
        mock_thread = MagicMock()
        sp._thread = mock_thread

        with patch.object(Path, "exists", return_value=False):
            sp.stop()

        mock_thread.join.assert_called_once_with(timeout=2)

    def test_stop_without_thread(self):
        """stop() when _thread is None must not raise."""
        sp = StatusPublisher(lambda: {})
        sp._running = True
        sp._thread = None
        with patch.object(Path, "exists", return_value=False):
            sp.stop()  # must not raise

    def test_stop_removes_status_file_if_exists(self):
        sp = StatusPublisher(lambda: {})
        sp._thread = None

        with patch.object(Path, "exists", return_value=True) as mock_exists, \
             patch.object(Path, "unlink") as mock_unlink:
            sp.stop()

        mock_exists.assert_called_once()
        mock_unlink.assert_called_once_with(missing_ok=True)

    def test_stop_skips_unlink_when_file_absent(self):
        sp = StatusPublisher(lambda: {})
        sp._thread = None

        with patch.object(Path, "exists", return_value=False), \
             patch.object(Path, "unlink") as mock_unlink:
            sp.stop()

        mock_unlink.assert_not_called()


# ---------------------------------------------------------------------------
# _publish_loop()
# ---------------------------------------------------------------------------

class TestStatusPublisherPublishLoop:
    """_publish_loop writes status JSON until _running goes False."""

    @patch("time.sleep", side_effect=StopIteration)
    @patch.object(Path, "write_text")
    def test_publish_loop_writes_status_json(self, mock_write, mock_sleep):
        status = {"state": "ready"}
        sp = StatusPublisher(lambda: status)
        sp._running = True

        with pytest.raises(StopIteration):
            sp._publish_loop()

        written = mock_write.call_args[0][0]
        assert json.loads(written) == status

    @patch("time.sleep", side_effect=StopIteration)
    @patch.object(Path, "write_text")
    def test_publish_loop_calls_get_status(self, mock_write, mock_sleep):
        getter = MagicMock(return_value={"x": 1})
        sp = StatusPublisher(getter)
        sp._running = True

        with pytest.raises(StopIteration):
            sp._publish_loop()

        getter.assert_called_once()

    @patch("time.sleep")
    @patch.object(Path, "write_text")
    def test_publish_loop_sleeps_one_second(self, mock_write, mock_sleep):
        call_count = 0

        def stop_after_one(*_a, **_kw):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                raise StopIteration

        mock_sleep.side_effect = stop_after_one
        sp = StatusPublisher(lambda: {})
        sp._running = True

        with pytest.raises(StopIteration):
            sp._publish_loop()

        mock_sleep.assert_called_with(1.0)

    @patch("time.sleep", side_effect=StopIteration)
    @patch.object(Path, "write_text", side_effect=OSError("disk full"))
    def test_publish_loop_swallows_write_error(self, mock_write, mock_sleep):
        """Exception in write_text is caught; loop continues to sleep."""
        sp = StatusPublisher(lambda: {})
        sp._running = True

        # StopIteration from sleep proves the loop survived the OSError
        with pytest.raises(StopIteration):
            sp._publish_loop()

    @patch("time.sleep", side_effect=StopIteration)
    @patch.object(Path, "write_text")
    def test_publish_loop_swallows_get_status_error(self, mock_write, mock_sleep):
        """Exception in get_status is caught; loop continues to sleep."""
        sp = StatusPublisher(MagicMock(side_effect=RuntimeError("boom")))
        sp._running = True

        with pytest.raises(StopIteration):
            sp._publish_loop()

        # write_text should NOT be called because get_status raised first
        mock_write.assert_not_called()

    @patch("time.sleep")
    @patch.object(Path, "write_text")
    def test_publish_loop_exits_when_running_false(self, mock_write, mock_sleep):
        sp = StatusPublisher(lambda: {})
        sp._running = False
        sp._publish_loop()  # should return immediately
        mock_write.assert_not_called()
        mock_sleep.assert_not_called()

    @patch("time.sleep")
    @patch.object(Path, "write_text")
    def test_publish_loop_multiple_iterations(self, mock_write, mock_sleep):
        iteration = 0

        def tick(_):
            nonlocal iteration
            iteration += 1
            if iteration >= 3:
                raise StopIteration

        mock_sleep.side_effect = tick
        counter = MagicMock(return_value={"i": 0})
        sp = StatusPublisher(counter)
        sp._running = True

        with pytest.raises(StopIteration):
            sp._publish_loop()

        assert counter.call_count == 3
        assert mock_write.call_count == 3


# ---------------------------------------------------------------------------
# STATUS_FILE constant
# ---------------------------------------------------------------------------

class TestStatusFileConstant:
    """STATUS_FILE points to ~/.windowsmcp/status.json."""

    def test_status_file_path(self):
        expected = Path.home() / ".windowsmcp" / "status.json"
        assert STATUS_FILE == expected

    def test_status_file_name(self):
        assert STATUS_FILE.name == "status.json"
