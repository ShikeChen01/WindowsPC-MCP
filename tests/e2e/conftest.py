"""Shared E2E fixtures -- full server stack without real MCP transport or Win32 calls."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest
from fastmcp import FastMCP

from windowspc_mcp.confinement.engine import ConfinementEngine
from windowspc_mcp.confinement.guard import ToolGuard
from windowspc_mcp.display.manager import DisplayInfo, DisplayManager
from windowspc_mcp.input.service import AgentInputService
from windowspc_mcp.server import ServerState, ServerStateManager
from windowspc_mcp.tools import register_all


# ---------------------------------------------------------------------------
# Mock display data
# ---------------------------------------------------------------------------

PRIMARY_DISPLAY = DisplayInfo(
    device_name=r"\\.\DISPLAY1",
    x=0,
    y=0,
    width=1920,
    height=1080,
    is_agent=False,
)

SECONDARY_DISPLAY = DisplayInfo(
    device_name=r"\\.\DISPLAY2",
    x=1920,
    y=0,
    width=1920,
    height=1080,
    is_agent=False,
)


@pytest.fixture
def mock_display():
    """An agent-flagged virtual display placed to the right of two monitors."""
    return DisplayInfo(
        device_name=r"\\.\DISPLAY3",
        x=3840,
        y=0,
        width=1920,
        height=1080,
        is_agent=True,
    )


@pytest.fixture
def monitor_list(mock_display):
    """Realistic monitor set: primary + secondary + agent."""
    return [PRIMARY_DISPLAY, SECONDARY_DISPLAY, mock_display]


# ---------------------------------------------------------------------------
# Core component fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def state_manager():
    return ServerStateManager()


@pytest.fixture
def display_manager(mock_display, monitor_list):
    """Real DisplayManager with Win32 boundary mocked out."""
    dm = DisplayManager()

    # Patch Win32-only methods
    dm.check_driver = MagicMock(return_value=True)
    dm.enumerate_monitors = MagicMock(return_value=list(monitor_list))

    # create_display: simulate creating a virtual display without real VDD
    def _fake_create(width: int = 1920, height: int = 1080) -> DisplayInfo:
        if dm._agent_display is not None:
            raise RuntimeError("Agent display already exists; destroy it first.")
        info = DisplayInfo(
            device_name=mock_display.device_name,
            x=mock_display.x,
            y=mock_display.y,
            width=width,
            height=height,
            is_agent=True,
        )
        dm._agent_display = info
        return info

    dm.create_display = MagicMock(side_effect=_fake_create)

    # destroy_display: clear state without real VDD teardown
    def _fake_destroy():
        dm._agent_display = None

    dm.destroy_display = MagicMock(side_effect=_fake_destroy)

    return dm


@pytest.fixture
def confinement():
    return ConfinementEngine()


@pytest.fixture
def guard(state_manager, confinement):
    return ToolGuard(state_manager, confinement)


@pytest.fixture
def input_service(confinement):
    return AgentInputService(agent_bounds_fn=lambda: confinement.bounds)


@pytest.fixture
def app_context(state_manager, display_manager, confinement, guard, input_service):
    """Full AppContext wired with real components (Win32 boundary mocked)."""
    from windowspc_mcp.__main__ import AppContext

    return AppContext(
        state_manager=state_manager,
        display_manager=display_manager,
        confinement=confinement,
        guard=guard,
        input_service=input_service,
    )


# ---------------------------------------------------------------------------
# Tool registry fixture
# ---------------------------------------------------------------------------


def _extract_tools(mcp: FastMCP) -> dict[str, callable]:
    """Extract registered tool functions by name from a FastMCP instance.

    Uses the async local_provider API via asyncio.run to list tools,
    then builds a plain dict of {name: fn}.
    """
    async def _gather():
        tools_list = await mcp.local_provider.list_tools()
        result = {}
        for t in tools_list:
            result[t.name] = t.fn
        return result

    # If there's already a running loop (e.g. pytest-asyncio), create a new one
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None:
        # We're inside an existing event loop; run in a new thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, _gather()).result()
    else:
        return asyncio.run(_gather())


@pytest.fixture
def registered_tools(display_manager, confinement, state_manager, guard, input_service):
    """Register all tools on a fresh FastMCP instance and expose them by name.

    Returns a dict mapping tool name -> callable, so tests can invoke
    ``tools["CreateScreen"](width=1920, height=1080)`` directly.
    """
    mcp = FastMCP(name="test-mcp")

    # Factory closures identical to __main__.py but pointing at fixture instances
    register_all(
        mcp,
        get_display_manager=lambda: display_manager,
        get_confinement=lambda: confinement,
        get_state_manager=lambda: state_manager,
        get_guard=lambda: guard,
        get_input_service=lambda: input_service,
    )

    return _extract_tools(mcp)
