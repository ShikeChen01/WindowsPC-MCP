# Error Responses + InputStatus — `desktop/responses.py` + `tools/input_status.py`

## format_gate_error (responses.py)

Converts InputGate exceptions into MCP-friendly response dicts.

```python
def format_gate_error(error: Exception) -> dict
```

| Exception | Response |
|-----------|----------|
| `AgentPreempted` | `{"error": "HUMAN_OVERRIDE", "message": "User has taken control. Retry when released."}` |
| `AgentPaused` | `{"error": "AGENT_PAUSED", "message": "Agent is paused. Waiting for user to resume."}` |
| `EmergencyStop` | `{"error": "EMERGENCY_STOP", "message": "Session terminated by user."}` |
| Other | Re-raised (not our concern) |

Pure function, no state, no dependencies beyond error types.

## InputStatus MCP Tool (tools/input_status.py)

Exposes the current input system state to the LLM so it can react to mode changes.

```python
def register_input_status_tool(gate: InputGate) -> Callable
    # Returns an async function suitable for FastMCP registration
```

Response format:

```json
{
    "mode": "cowork",
    "agent_can_input": true,
    "description": "Shared desktop. Agent input is scheduled around human activity."
}
```

`agent_can_input` is `true` only for AGENT_SOLO and COWORK.

### Mode Descriptions

| Mode | Description |
|------|-------------|
| AGENT_SOLO | Agent has full control of its desktop. No scheduling needed. |
| COWORK | Shared desktop. Agent input is scheduled around human activity. |
| HUMAN_OVERRIDE | Human has taken control. Agent input is blocked until released. |
| HUMAN_HOME | User's desktop is active. Agent is paused. |
| EMERGENCY_STOP | Session terminated. No recovery possible. |

### Which Tools Are Gated

**Gated by InputGate** (go through check()): Click, Type, Move, Scroll, Shortcut, MultiEdit, MultiSelect — anything that sends input.

**Not gated** (work in all modes): Screenshot, Snapshot, Scrape, FileSystem, PowerShell, Process, Registry, Clipboard, App, Notification, InputStatus. The agent can still observe and think while paused.
