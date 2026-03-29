"""Decorators that enforce confinement policy on MCP tools."""

import functools
import logging
from typing import Callable

from windowspc_mcp.confinement.errors import InvalidStateError, WindowsMCPError

logger = logging.getLogger(__name__)


def guarded_tool(get_guard: Callable):
    """Decorator that checks ToolGuard before executing a tool.

    Catches all WindowsMCPError subclasses and returns them as error strings
    (MCP tools return strings, not exceptions).

    Usage:
        @mcp.tool(name="Click", ...)
        @guarded_tool(get_guard)
        def click(x: int, y: int) -> str:
            ...
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Run guard check
            guard = get_guard() if callable(get_guard) else None
            if guard is not None:
                err = guard.check(func.__name__ if not hasattr(func, '_tool_name') else func._tool_name)
                if err:
                    return err
            try:
                return func(*args, **kwargs)
            except WindowsMCPError as e:
                return f"Error: {e}"
        return wrapper
    return decorator


def with_tool_name(name: str):
    """Set the tool name for guard checking (since func.__name__ may differ from MCP tool name)."""
    def decorator(func):
        func._tool_name = name
        return func
    return decorator
