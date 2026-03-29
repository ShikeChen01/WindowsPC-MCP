"""Clipboard tool: get and set clipboard text."""

from __future__ import annotations

from typing import Optional

from windowsmcp_custom.confinement.decorators import guarded_tool, with_tool_name


def register(mcp, *, get_display_manager, get_confinement, get_state_manager=None, get_guard=None, get_input_service=None):
    """Register the Clipboard tool."""

    @mcp.tool(
        name="Clipboard",
        description=(
            "Read from or write to the Windows clipboard (text only). "
            "action: 'get' (default) returns current clipboard text; "
            "'set' writes content to the clipboard."
        ),
    )
    @guarded_tool(get_guard)
    @with_tool_name("Clipboard")
    def clipboard(action: str = "get", content: Optional[str] = None) -> str:
        action = action.lower().strip()

        try:
            import win32clipboard
            import win32con

            if action == "get":
                win32clipboard.OpenClipboard()
                try:
                    if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                        text = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
                        return text if text else "(empty clipboard)"
                    else:
                        return "(clipboard does not contain text)"
                finally:
                    win32clipboard.CloseClipboard()

            elif action == "set":
                if content is None:
                    return "Error: 'content' is required for set."
                win32clipboard.OpenClipboard()
                try:
                    win32clipboard.EmptyClipboard()
                    win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, content)
                finally:
                    win32clipboard.CloseClipboard()
                return f"Clipboard set ({len(content)} character(s))."

            else:
                return f"Error: unknown action '{action}'. Use 'get' or 'set'."

        except ImportError:
            return "Error: win32clipboard not available (install pywin32)."
        except Exception as e:
            return f"Error: {e}"
