"""Entry point for the WindowsMCP Custom server."""

import logging
from contextlib import asynccontextmanager
from typing import Optional

import click
from fastmcp import FastMCP

from windowsmcp_custom.display.manager import DisplayManager
from windowsmcp_custom.confinement.engine import ConfinementEngine
from windowsmcp_custom.confinement.bounds import (
    DisplayChangeListener,
    WTS_SESSION_LOCK,
    WTS_SESSION_UNLOCK,
)
from windowsmcp_custom.server import ServerStateManager, ServerState
from windowsmcp_custom.ipc.status import StatusPublisher
from windowsmcp_custom.tools import register_all

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------

display_manager: Optional[DisplayManager] = None
confinement: Optional[ConfinementEngine] = None
state_manager: Optional[ServerStateManager] = None
display_listener: Optional[DisplayChangeListener] = None


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastMCP):
    """Initialize and clean up server components."""
    global display_manager, confinement, state_manager, display_listener

    # --- Startup ---
    state_manager = ServerStateManager()
    display_manager = DisplayManager()
    confinement = ConfinementEngine()

    # Check for Parsec VDD driver
    if display_manager.check_driver():
        state_manager.transition(ServerState.READY)
        logger.info("Parsec VDD driver found — server is READY")
    else:
        state_manager.transition(
            ServerState.DRIVER_MISSING,
            reason="Parsec VDD driver not found; install it before calling CreateScreen",
        )
        logger.warning(
            "Parsec VDD driver not found. Install the driver and restart the server. "
            "Most tools are unavailable until a virtual display is created."
        )

    # --- Display-change callbacks ---

    def on_display_change() -> None:
        """Refresh bounds and update confinement when monitors change."""
        assert display_manager is not None
        assert confinement is not None
        assert state_manager is not None

        display_manager.refresh_bounds()
        agent = display_manager.agent_display
        if agent is not None:
            confinement.set_agent_bounds(agent)
            logger.debug("Display change: refreshed agent bounds to %dx%d", agent.width, agent.height)
        else:
            confinement.clear_bounds()
            if state_manager.state not in (
                ServerState.SHUTTING_DOWN,
                ServerState.DRIVER_MISSING,
            ):
                state_manager.transition(
                    ServerState.DEGRADED, reason="Agent display lost after display-change event"
                )
                logger.warning("Agent display lost; transitioning to DEGRADED")

    def on_session_change(event_id: int) -> None:
        """Transition state on Windows session lock/unlock."""
        assert state_manager is not None

        if event_id == WTS_SESSION_LOCK:
            if state_manager.state not in (
                ServerState.SHUTTING_DOWN,
                ServerState.DRIVER_MISSING,
            ):
                state_manager.transition(ServerState.DEGRADED, reason="Session locked")
                logger.info("Session locked; transitioning to DEGRADED")
        elif event_id == WTS_SESSION_UNLOCK:
            if state_manager.state == ServerState.DEGRADED:
                state_manager.transition(ServerState.READY)
                logger.info("Session unlocked; transitioning back to READY")

    # --- Start display change listener ---
    display_listener = DisplayChangeListener(
        on_display_change=on_display_change,
        on_session_change=on_session_change,
    )
    display_listener.start()

    # --- Start status publisher ---
    publisher = StatusPublisher(state_manager.get_status)
    publisher.start()

    try:
        yield
    finally:
        # --- Shutdown ---
        state_manager.transition(ServerState.SHUTTING_DOWN)
        logger.info("Server shutting down")

        if display_listener is not None:
            display_listener.stop()
            display_listener = None

        publisher.stop()

        if display_manager is not None and display_manager.is_ready:
            display_manager.destroy_display()


# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name="windowsmcp-custom",
    instructions=(
        "WindowsMCP Custom provides tools to interact with a confined virtual display. "
        "The agent operates on a dedicated virtual screen isolated from the user's physical monitors. "
        "Always call CreateScreen first to set up the agent display before using any GUI tools. "
        "All coordinate arguments are relative to the virtual screen (top-left is 0,0). "
        "Use Screenshot with screen='all' to capture the full desktop and detect pop-up windows "
        "or dialogs that may have appeared outside the virtual screen."
    ),
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------


def _get_display_manager() -> Optional[DisplayManager]:
    return display_manager


def _get_confinement() -> Optional[ConfinementEngine]:
    return confinement


# ---------------------------------------------------------------------------
# Register all tool modules
# ---------------------------------------------------------------------------

register_all(mcp, get_display_manager=_get_display_manager, get_confinement=_get_confinement)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command()
@click.option(
    "--transport",
    type=click.Choice(["stdio", "sse"]),
    default="stdio",
    help="Transport protocol (stdio for Claude Desktop, sse for HTTP clients).",
)
@click.option("--host", default="localhost", type=str, help="Host to bind to (sse only).")
@click.option("--port", default=8000, type=int, help="Port to listen on (sse only).")
def main(transport: str, host: str, port: int) -> None:
    """Start the WindowsMCP Custom server."""
    kwargs = {"transport": transport, "show_banner": False}
    if transport == "sse":
        kwargs["host"] = host
        kwargs["port"] = port
    mcp.run(**kwargs)


if __name__ == "__main__":
    main()
