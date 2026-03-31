"""Tests for CursorScheduler -- dispatch loop with cursor lock."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, call

import pytest

from windowspc_mcp.confinement.errors import AgentPreempted, InvalidStateError
from windowspc_mcp.desktop.profiler import ActionProfiler, ActionType
from windowspc_mcp.desktop.scheduler import CursorScheduler, Instruction


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_scheduler(
    agent_can_fire: bool = True,
) -> tuple[CursorScheduler, MagicMock, MagicMock]:
    """Create a scheduler with mock monitor and profiler.

    Returns (scheduler, mock_monitor, mock_profiler).
    """
    monitor = MagicMock()
    monitor.agent_can_fire.return_value = agent_can_fire
    profiler = MagicMock(spec=ActionProfiler)
    scheduler = CursorScheduler(monitor, profiler)
    return scheduler, monitor, profiler


# ---------------------------------------------------------------------------
# Tests: Instruction
# ---------------------------------------------------------------------------


class TestInstruction:
    def test_set_result_and_wait(self):
        instr = Instruction(ActionType.CLICK, lambda: None)
        instr.set_result(42)
        assert instr.wait(timeout=1.0) == 42

    def test_set_error_and_wait(self):
        instr = Instruction(ActionType.CLICK, lambda: None)
        instr.set_error(ValueError("boom"))
        with pytest.raises(ValueError, match="boom"):
            instr.wait(timeout=1.0)

    def test_wait_timeout(self):
        instr = Instruction(ActionType.CLICK, lambda: None)
        with pytest.raises(TimeoutError, match="timed out"):
            instr.wait(timeout=0.01)


# ---------------------------------------------------------------------------
# Tests: start/stop lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    def test_start_sets_running(self):
        sched, _, _ = _make_scheduler()
        sched.start()
        assert sched.is_running is True
        sched.stop()

    def test_stop_clears_running(self):
        sched, _, _ = _make_scheduler()
        sched.start()
        sched.stop()
        assert sched.is_running is False

    def test_stop_when_not_started_is_safe(self):
        sched, _, _ = _make_scheduler()
        sched.stop()  # Should not raise

    def test_double_start_raises(self):
        sched, _, _ = _make_scheduler()
        sched.start()
        try:
            with pytest.raises(InvalidStateError, match="already running"):
                sched.start()
        finally:
            sched.stop()

    def test_restart_after_stop(self):
        sched, _, _ = _make_scheduler()
        sched.start()
        sched.stop()
        # Should be able to start again
        sched.start()
        assert sched.is_running is True
        sched.stop()


# ---------------------------------------------------------------------------
# Tests: submit
# ---------------------------------------------------------------------------


class TestSubmit:
    def test_submit_executes_and_returns_result(self):
        sched, _, _ = _make_scheduler(agent_can_fire=True)
        sched.start()
        try:
            result = sched.submit(ActionType.CLICK, lambda: "hello", timeout=2.0)
            assert result == "hello"
        finally:
            sched.stop()

    def test_submit_raises_errors_from_execute_fn(self):
        def bad_fn():
            raise RuntimeError("kaboom")

        sched, _, _ = _make_scheduler(agent_can_fire=True)
        sched.start()
        try:
            with pytest.raises(RuntimeError, match="kaboom"):
                sched.submit(ActionType.CLICK, bad_fn, timeout=2.0)
        finally:
            sched.stop()

    def test_submit_when_not_running_raises(self):
        sched, _, _ = _make_scheduler()
        with pytest.raises(InvalidStateError, match="not running"):
            sched.submit(ActionType.CLICK, lambda: None)

    def test_submit_times_out_when_gap_never_opens(self):
        sched, _, _ = _make_scheduler(agent_can_fire=False)
        sched.start()
        try:
            with pytest.raises(TimeoutError):
                sched.submit(ActionType.CLICK, lambda: None, timeout=0.05)
        finally:
            sched.stop()


# ---------------------------------------------------------------------------
# Tests: stop rejects pending
# ---------------------------------------------------------------------------


class TestStopRejectsPending:
    def test_stop_rejects_pending_with_agent_preempted(self):
        sched, _, _ = _make_scheduler(agent_can_fire=False)
        sched.start()

        # Submit in a background thread (it will block because gap never opens)
        result_holder: dict = {"error": None}
        submitted = threading.Event()

        def submitter():
            try:
                sched.submit(ActionType.CLICK, lambda: None, timeout=5.0)
            except Exception as e:
                result_holder["error"] = e

        t = threading.Thread(target=submitter)
        t.start()

        # Give the submit time to enqueue
        time.sleep(0.05)

        # Stop should reject the pending instruction
        sched.stop()
        t.join(timeout=2.0)
        assert not t.is_alive()
        assert isinstance(result_holder["error"], AgentPreempted)


# ---------------------------------------------------------------------------
# Tests: dispatch respects monitor
# ---------------------------------------------------------------------------


class TestMonitorRespect:
    def test_dispatch_waits_for_agent_can_fire(self):
        """Instructions only execute when monitor says agent_can_fire."""
        sched, monitor, _ = _make_scheduler(agent_can_fire=False)
        sched.start()

        executed = threading.Event()

        def action():
            executed.set()
            return "done"

        # Submit in background -- will block
        result_holder: dict = {"result": None}

        def submitter():
            result_holder["result"] = sched.submit(
                ActionType.CLICK, action, timeout=2.0,
            )

        t = threading.Thread(target=submitter)
        t.start()

        # Wait a bit -- should NOT have executed
        time.sleep(0.05)
        assert not executed.is_set()

        # Now allow firing
        monitor.agent_can_fire.return_value = True
        t.join(timeout=2.0)
        assert not t.is_alive()
        assert executed.is_set()
        assert result_holder["result"] == "done"
        sched.stop()


# ---------------------------------------------------------------------------
# Tests: profiler recording
# ---------------------------------------------------------------------------


class TestProfilerRecording:
    def test_profiler_record_called_with_action_type(self):
        sched, _, profiler = _make_scheduler(agent_can_fire=True)
        sched.start()
        try:
            sched.submit(ActionType.MOVE, lambda: None, timeout=2.0)
            # Give the dispatch loop time to complete
            time.sleep(0.02)
        finally:
            sched.stop()

        profiler.record.assert_called_once()
        call_args = profiler.record.call_args
        assert call_args[0][0] == ActionType.MOVE
        # Second arg is actual_ms (a positive float)
        assert call_args[0][1] >= 0.0

    def test_profiler_record_called_even_on_error(self):
        def bad_fn():
            raise ValueError("oops")

        sched, _, profiler = _make_scheduler(agent_can_fire=True)
        sched.start()
        try:
            with pytest.raises(ValueError):
                sched.submit(ActionType.KEY, bad_fn, timeout=2.0)
            time.sleep(0.02)
        finally:
            sched.stop()

        profiler.record.assert_called_once()
        assert profiler.record.call_args[0][0] == ActionType.KEY


# ---------------------------------------------------------------------------
# Tests: cursor_lock held during execution
# ---------------------------------------------------------------------------


class TestCursorLock:
    def test_cursor_lock_held_during_execution(self):
        sched, _, _ = _make_scheduler(agent_can_fire=True)
        sched.start()

        lock_was_held = threading.Event()

        def check_lock():
            # Try to acquire the cursor lock with a very short timeout.
            # If it's held by _fire, acquire should fail.
            acquired = sched._cursor_lock.acquire(timeout=0)
            if not acquired:
                lock_was_held.set()
            else:
                sched._cursor_lock.release()

        def slow_action():
            # While this runs, the lock should be held.
            # Spawn a thread to verify.
            checker = threading.Thread(target=check_lock)
            checker.start()
            # Give the checker thread time to try acquiring
            time.sleep(0.02)
            checker.join(timeout=1.0)
            return "ok"

        try:
            result = sched.submit(ActionType.CLICK, slow_action, timeout=2.0)
            assert result == "ok"
            assert lock_was_held.is_set(), "cursor_lock was not held during execution"
        finally:
            sched.stop()


# ---------------------------------------------------------------------------
# Tests: queue_depth
# ---------------------------------------------------------------------------


class TestQueueDepth:
    def test_queue_depth_zero_initially(self):
        sched, _, _ = _make_scheduler()
        assert sched.queue_depth == 0

    def test_queue_depth_reflects_pending(self):
        sched, _, _ = _make_scheduler(agent_can_fire=False)
        sched.start()

        # Submit multiple instructions in background threads (they will block)
        threads = []
        for _ in range(3):
            t = threading.Thread(
                target=lambda: _ignore_errors(
                    lambda: sched.submit(ActionType.CLICK, lambda: None, timeout=1.0),
                ),
            )
            t.start()
            threads.append(t)

        # Give time for all submits to enqueue
        time.sleep(0.05)
        assert sched.queue_depth == 3

        sched.stop()
        for t in threads:
            t.join(timeout=2.0)


# ---------------------------------------------------------------------------
# Tests: FIFO ordering
# ---------------------------------------------------------------------------


class TestFIFOOrder:
    def test_multiple_instructions_execute_in_fifo_order(self):
        sched, monitor, _ = _make_scheduler(agent_can_fire=False)
        sched.start()

        order: list[int] = []
        order_lock = threading.Lock()

        def make_action(i: int):
            def action():
                with order_lock:
                    order.append(i)
                return i
            return action

        threads = []
        for i in range(5):
            t = threading.Thread(
                target=lambda idx=i: _ignore_errors(
                    lambda: sched.submit(
                        ActionType.CLICK, make_action(idx), timeout=2.0,
                    ),
                ),
            )
            t.start()
            threads.append(t)
            # Small delay to ensure ordering in the deque
            time.sleep(0.01)

        # Ensure all are enqueued
        time.sleep(0.02)

        # Now open the gate
        monitor.agent_can_fire.return_value = True

        for t in threads:
            t.join(timeout=3.0)

        sched.stop()

        assert order == [0, 1, 2, 3, 4]


# ---------------------------------------------------------------------------
# Tests: complexity passthrough
# ---------------------------------------------------------------------------


class TestComplexity:
    def test_instruction_stores_complexity(self):
        instr = Instruction(ActionType.STRING, lambda: None, complexity=3.5)
        assert instr.complexity == 3.5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ignore_errors(fn):
    """Call fn and swallow any exception."""
    try:
        fn()
    except Exception:
        pass
