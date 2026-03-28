"""MCP tool registry."""

from windowsmcp_custom.tools import (
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


def register_all(mcp, *, get_display_manager, get_confinement):
    """Register all tool modules with the MCP server."""
    for mod in _MODULES:
        mod.register(mcp, get_display_manager=get_display_manager, get_confinement=get_confinement)
