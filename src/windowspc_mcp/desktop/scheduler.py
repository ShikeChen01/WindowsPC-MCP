"""CursorScheduler -- dispatch loop with cursor lock for COWORK mode.

Queues agent instructions, waits for human idle gaps (via InputDecayMonitor),
and executes them with an exclusive cursor lock.

Core rule: when the agent fires, human is locked out.  When human is active,
agent waits.  Hotkey overrides everything.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any, Callable

from windowspc_mcp.confinement.errors import AgentPreempted, InvalidStateError
from windowspc_mcp.desktop.monitor import InputDecayMonitor
from windowspc_mcp.desktop.profiler import ActionProfiler, ActionType


class Instruction:
    """An agent input operation waiting to be executed."""

    def __init__(
        self,
        action_type: ActionType,
        execute_fn: Callable[[], Any],
        complexity: float = 1.0,
    ) -> None:
        self.action_type = action_type
        self.execute_fn = execute_fn
        self.complexity = complexity
        self._result: Any = None
        self._error: Exception | None = None
        self._done = threading.Event()

    def set_result(self, result: Any) -> None:
        self._result = result
        self._done.set()

    def set_error(self, error: Exception) -> None:
        self._error = error
        self._done.set()

    def wait(self, timeout: float | None = None) -> Any:
        """Block until instruction is executed. Returns result or raises error."""
        if not self._done.wait(timeout):
            raise TimeoutError("Instruction timed out waiting for execution")
        if self._error:
            raise self._error
        return self._result


class CursorScheduler:
    """Dispatches agent instructions into human idle gaps.

    Instruction lifecycle:
    1. MCP tool calls submit() -- instruction queued
    2. Dispatch loop detects idle gap (monitor.agent_can_fire())
    3. Acquires cursor lock -- human frozen
    4. Executes instruction
    5. Records actual time -- profiler
    6. Releases cursor lock -- human unfrozen
    7. submit() returns result to MCP tool
    """

    POLL_INTERVAL_MS = 5  # How often to check for gaps
    DEFAULT_TIMEOUT_S = 10.0  # Max time an instruction waits before timeout

    def __init__(self, monitor: InputDecayMonitor, profiler: ActionProfiler) -> None:
        self._monitor = monitor
        self._profiler = profiler
        self._queue: deque[Instruction] = deque()
        self._cursor_lock = threading.Lock()  # When held, human cursor frozen
        self._running = False
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        """Start the dispatch loop thread."""
        if self._running:
            raise InvalidStateError("Scheduler already running")
        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(
            target=self._dispatch_loop, daemon=True, name="cursor-scheduler",
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the dispatch loop. Reject all pending instructions."""
        self._running = False
        self._stop_event.set()
        # Drain queue -- reject pending instructions
        while self._queue:
            instruction = self._queue.popleft()
            instruction.set_error(AgentPreempted("Scheduler stopped"))
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None

    def submit(
        self,
        action_type: ActionType,
        execute_fn: Callable[[], Any],
        complexity: float = 1.0,
        timeout: float | None = None,
    ) -> Any:
        """Submit an instruction and block until executed.

        Called by MCP tools in COWORK mode.
        Returns the result of execute_fn.
        Raises AgentPreempted if scheduler stops while waiting.
        Raises TimeoutError if instruction doesn't execute in time.
        """
        if not self._running:
            raise InvalidStateError("Scheduler not running")

        instruction = Instruction(action_type, execute_fn, complexity)
        self._queue.append(instruction)
        return instruction.wait(timeout or self.DEFAULT_TIMEOUT_S)

    def _dispatch_loop(self) -> None:
        """Background thread. Polls for gaps and dispatches instructions."""
        while not self._stop_event.is_set():
            if not self._queue:
                self._stop_event.wait(self.POLL_INTERVAL_MS / 1000)
                continue

            if self._monitor.agent_can_fire():
                instruction = self._queue[0]
                self._fire(instruction)
                self._queue.popleft()
            else:
                self._stop_event.wait(self.POLL_INTERVAL_MS / 1000)

    def _fire(self, instruction: Instruction) -> None:
        """Lock cursor, execute, release."""
        with self._cursor_lock:
            start = time.perf_counter_ns()
            try:
                result = instruction.execute_fn()
                instruction.set_result(result)
            except Exception as e:
                instruction.set_error(e)
            finally:
                actual_ms = (time.perf_counter_ns() - start) / 1_000_000
                self._profiler.record(instruction.action_type, actual_ms)

    @property
    def queue_depth(self) -> int:
        """Number of pending instructions."""
        return len(self._queue)

    @property
    def is_running(self) -> bool:
        return self._running
