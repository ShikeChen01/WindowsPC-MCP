# CursorScheduler — `desktop/scheduler.py`

The COWORK dispatch loop. Queues agent instructions, waits for human idle gaps, and executes them with an exclusive cursor lock.

## Core Rule

**When the agent fires, human is locked out. When human is active, agent waits.**

## Instruction Lifecycle

```
MCP tool calls submit()
        │
        ▼
   Instruction queued (FIFO)
        │
        ▼
   Dispatch loop (5ms poll):
   ┌─ monitor.agent_can_fire()? ─┐
   │                              │
   YES                            NO
   │                              │ wait 5ms, retry
   ▼                              │
   ACQUIRE cursor_lock            │
   │                              │
   Human cursor frozen.           │
   Execute instruction.           │
   Record actual_ms → profiler.   │
   │                              │
   RELEASE cursor_lock            │
   │                              │
   Human unfrozen.                │
   Return result to submit().     │
   Next instruction. ─────────────┘
```

## Public API

```python
class Instruction:
    def __init__(self, action_type, execute_fn, complexity=1.0)
    def set_result(result)     # Called by scheduler after execution
    def set_error(error)       # Called on failure or preemption
    def wait(timeout) -> Any   # Blocks caller until done

class CursorScheduler:
    POLL_INTERVAL_MS = 5
    DEFAULT_TIMEOUT_S = 10.0

    def start(self) -> None
        # Starts daemon dispatch thread

    def stop(self) -> None
        # Signals stop, rejects all pending with AgentPreempted, joins thread

    def submit(self, action_type, execute_fn, complexity=1.0, timeout=None) -> Any
        # Enqueues instruction, blocks until executed
        # Returns execute_fn's return value
        # Raises AgentPreempted if stopped while waiting
        # Raises TimeoutError if gap never opens

    @property queue_depth -> int
    @property is_running -> bool
```

## Cursor Lock Contract

- **While held:** Human physical input is queued by the OS (cursor doesn't move)
- **Typical duration:** <1ms move, <3ms click, <5ms short string, up to 50ms long type
- **Non-reentrant:** One instruction at a time
- **Between instructions:** Lock is released, giving human a window to reclaim

## submit() Blocking

`submit()` creates an `Instruction`, appends to deque, then calls `instruction.wait(timeout)`. The wait blocks on a `threading.Event` that the dispatch thread sets after execution. This makes the MCP tool call synchronous from the caller's perspective.

## Stop Behavior

`stop()` sets `_stop_event`, which the dispatch loop checks every 5ms. All pending instructions in the queue receive `AgentPreempted` errors. The dispatch thread joins within 5 seconds.
