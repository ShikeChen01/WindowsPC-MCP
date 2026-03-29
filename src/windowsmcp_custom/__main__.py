"""Entry point for the WindowsMCP Custom server."""

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
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
from windowsmcp_custom.confinement.guard import ToolGuard
from windowsmcp_custom.server import ServerStateManager, ServerState
from windowsmcp_custom.ipc.status import StatusPublisher
from windowsmcp_custom.tools import register_all

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# AppContext — single container for all server-level state
# ---------------------------------------------------------------------------


@dataclass
class AppContext:
    """Holds all server-level components for the lifetime of one lifespan."""

    state_manager: ServerStateManager
    display_manager: DisplayManager
    confinement: ConfinementEngine
    guard: ToolGuard
    status_publisher: Optional[StatusPublisher] = None
    display_listener: Optional[DisplayChangeListener] = None


# Single global context; None between server restarts
_ctx: Optional[AppContext] = None


# ---------------------------------------------------------------------------
# Factory functions used by tools
# ---------------------------------------------------------------------------


def _get_display_manager() -> Optional[DisplayManager]:
    return _ctx.display_manager if _ctx is not None else None


def _get_confinement() -> Optional[ConfinementEngine]:
    return _ctx.confinement if _ctx is not None else None


def _get_state_manager() -> Optional[ServerStateManager]:
    return _ctx.state_manager if _ctx is not None else None


def _get_guard() -> Optional[ToolGuard]:
    return _ctx.guard if _ctx is not None else None


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastMCP):
    """Initialize and clean up server components."""
    global _ctx

    # Track what was successfully started for targeted cleanup
    _publisher_started = False
    _listener_started = False

    # --- Build core components ---
    state_manager = ServerStateManager()
    display_manager = DisplayManager()
    confinement = ConfinementEngine()
    guard = ToolGuard(state_manager, confinement)

    _ctx = AppContext(
        state_manager=state_manager,
        display_manager=display_manager,
        confinement=confinement,
        guard=guard,
    )

    # --- Check for Parsec VDD driver ---
    # Keep state as INIT until CreateScreen is called. If driver is missing,
    # transition to DRIVER_MISSING so the guard can give appropriate messages.
    if display_manager.check_driver():
        logger.info(
            "Parsec VDD driver found — server ready for CreateScreen. "
            "Call CreateScreen to activate GUI tools."
        )
        # Stay in INIT — CreateScreen will transition to READY after display + bounds are set.
    else:
        state_manager.transition(
            ServerState.DRIVER_MISSING,
            reason="Parsec VDD driver not found; install it before calling CreateScreen",
        )
        logger.warning(
            "Parsec VDD driver not found. Install the driver and restart the server. "
            "Most tools are unavailable until a virtual display is created."
        )

    # --- Display-change callback ---

    def on_display_change() -> None:
        """Refresh bounds and update confinement when monitors change."""
        try:
            ctx = _ctx
            if ctx is None:
                return

            ctx.display_manager.refresh_bounds()
            agent = ctx.display_manager.agent_display
            if agent is not None:
                ctx.confinement.set_agent_bounds(agent)
                logger.debug(
                    "Display change: refreshed agent bounds to %dx%d",
                    agent.width,
                    agent.height,
                )
            else:
                ctx.confinement.clear_bounds()
                if ctx.state_manager.state not in (
                    ServerState.SHUTTING_DOWN,
                    ServerState.DRIVER_MISSING,
                ):
                    ctx.state_manager.transition(
                        ServerState.DEGRADED,
                        reason="Agent display lost after display-change event",
                    )
                    logger.warning("Agent display lost; transitioning to DEGRADED")
        except Exception:
            logger.exception("Unhandled error in on_display_change; transitioning to DEGRADED")
            try:
                if _ctx is not None:
                    _ctx.state_manager.transition(
                        ServerState.DEGRADED,
                        reason="Unexpected error in display-change handler",
                    )
            except Exception:
                logger.exception("Failed to transition to DEGRADED after on_display_change error")

    # --- Session-change callback ---

    def on_session_change(event_id: int) -> None:
        """Transition state on Windows session lock/unlock."""
        try:
            ctx = _ctx
            if ctx is None:
                return

            if event_id == WTS_SESSION_LOCK:
                if ctx.state_manager.state not in (
                    ServerState.SHUTTING_DOWN,
                    ServerState.DRIVER_MISSING,
                ):
                    ctx.state_manager.transition(ServerState.DEGRADED, reason="Session locked")
                    logger.info("Session locked; transitioning to DEGRADED")
            elif event_id == WTS_SESSION_UNLOCK:
                if ctx.state_manager.state == ServerState.DEGRADED:
                    ctx.state_manager.transition(ServerState.READY)
                    logger.info("Session unlocked; transitioning back to READY")
        except Exception:
            logger.exception("Unhandled error in on_session_change; ignoring")

    # --- Start display change listener ---
    display_listener = DisplayChangeListener(
        on_display_change=on_display_change,
        on_session_change=on_session_change,
    )
    display_listener.start()
    _listener_started = True
    _ctx.display_listener = display_listener

    # --- Start status publisher ---
    publisher = StatusPublisher(state_manager.get_status)
    publisher.start()
    _publisher_started = True
    _ctx.status_publisher = publisher

    try:
        yield
    finally:
        # --- Shutdown ---
        state_manager.transition(ServerState.SHUTTING_DOWN)
        logger.info("Server shutting down")

        if _listener_started and _ctx is not None and _ctx.display_listener is not None:
            _ctx.display_listener.stop()
            _ctx.display_listener = None

        if _publisher_started and _ctx is not None and _ctx.status_publisher is not None:
            _ctx.status_publisher.stop()

        if display_manager is not None and display_manager.is_ready:
            display_manager.destroy_display()

        _ctx = None


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
# Register all tool modules
# ---------------------------------------------------------------------------

register_all(
    mcp,
    get_display_manager=_get_display_manager,
    get_confinement=_get_confinement,
    get_state_manager=_get_state_manager,
    get_guard=_get_guard,
)


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
