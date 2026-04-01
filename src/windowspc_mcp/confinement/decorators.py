"""Decorators that enforce confinement policy on MCP tools."""

import functools
import inspect
import logging
from typing import Callable

from windowspc_mcp.confinement.errors import WindowsMCPError

logger = logging.getLogger(__name__)


def _get_tool_name(func) -> str:
    """Return the tool name from _tool_name attribute or fall back to __name__."""
    return getattr(func, '_tool_name', func.__name__)


def guarded_tool(get_guard: Callable):
    """Decorator that checks ToolGuard before executing a tool.

    Catches all WindowsMCPError subclasses and returns them as error strings
    (MCP tools return strings, not exceptions).

    Supports both sync and async tool functions.

    Usage:
        @mcp.tool(name="Click", ...)
        @guarded_tool(get_guard)
        def click(x: int, y: int) -> str:
            ...

        @mcp.tool(name="Screenshot", ...)
        @guarded_tool(get_guard)
        async def screenshot() -> str:
            ...
    """
    def decorator(func):
        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                guard = get_guard() if callable(get_guard) else None
                if guard is not None:
                    tool_name = _get_tool_name(func)
                    err = guard.check(tool_name)
                    if err:
                        return err
                try:
                    return await func(*args, **kwargs)
                except WindowsMCPError as e:
                    return f"Error: {e}"
            return async_wrapper

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Run guard check
            guard = get_guard() if callable(get_guard) else None
            if guard is not None:
                tool_name = _get_tool_name(func)
                err = guard.check(tool_name)
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
