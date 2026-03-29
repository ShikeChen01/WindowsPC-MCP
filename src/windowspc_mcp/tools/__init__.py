"""MCP tool registry."""

from windowspc_mcp.tools import (
    screen,
    screenshot,
    input,
    app,
    multi,
    shell,
    filesystem,
    clipboard,
    process,
    registry,
    notification,
    scrape,
)

_MODULES = [
    screen,
    screenshot,
    input,
    app,
    multi,
    shell,
    filesystem,
    clipboard,
    process,
    registry,
    notification,
    scrape,
]


def register_all(mcp, *, get_display_manager, get_confinement, get_state_manager=None, get_guard=None, get_input_service=None):
    """Register all tool modules with the MCP server."""
    for mod in _MODULES:
        mod.register(
            mcp,
            get_display_manager=get_display_manager,
            get_confinement=get_confinement,
            get_state_manager=get_state_manager,
            get_guard=get_guard,
            get_input_service=get_input_service,
        )
