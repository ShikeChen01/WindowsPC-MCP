"""FileSystem tool: read, write, list, info, delete, copy, move."""

from __future__ import annotations

import os
import shutil
from typing import Optional

from windowsmcp_custom.confinement.decorators import guarded_tool, with_tool_name


def register(mcp, *, get_display_manager, get_confinement, get_state_manager=None, get_guard=None, get_input_service=None):
    """Register the FileSystem tool."""

    @mcp.tool(
        name="FileSystem",
        description=(
            "Perform filesystem operations. "
            "action: 'read', 'write', 'list', 'info', 'delete', 'copy', 'move'. "
            "path: target file or directory. "
            "content: text to write (for 'write'). "
            "destination: target path (for 'copy' and 'move')."
        ),
    )
    @guarded_tool(get_guard)
    @with_tool_name("FileSystem")
    def file_system(
        action: str,
        path: str,
        content: Optional[str] = None,
        destination: Optional[str] = None,
    ) -> str:
        action = action.lower().strip()

        try:
            if action == "read":
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    data = f.read()
                return data[:100_000]  # cap at 100k chars

            elif action == "write":
                if content is None:
                    return "Error: 'content' is required for write."
                os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                return f"Written {len(content)} character(s) to '{path}'."

            elif action == "list":
                if os.path.isdir(path):
                    entries = os.listdir(path)
                    lines = []
                    for entry in sorted(entries):
                        full = os.path.join(path, entry)
                        marker = "/" if os.path.isdir(full) else ""
                        lines.append(f"{entry}{marker}")
                    return "\n".join(lines) if lines else "(empty directory)"
                else:
                    return f"Error: '{path}' is not a directory."

            elif action == "info":
                stat = os.stat(path)
                kind = "directory" if os.path.isdir(path) else "file"
                return (
                    f"path: {os.path.abspath(path)}\n"
                    f"type: {kind}\n"
                    f"size: {stat.st_size} bytes\n"
                    f"modified: {stat.st_mtime}\n"
                )

            elif action == "delete":
                if os.path.isdir(path):
                    shutil.rmtree(path)
                    return f"Deleted directory '{path}'."
                else:
                    os.remove(path)
                    return f"Deleted file '{path}'."

            elif action == "copy":
                if destination is None:
                    return "Error: 'destination' is required for copy."
                if os.path.isdir(path):
                    shutil.copytree(path, destination)
                else:
                    shutil.copy2(path, destination)
                return f"Copied '{path}' to '{destination}'."

            elif action == "move":
                if destination is None:
                    return "Error: 'destination' is required for move."
                shutil.move(path, destination)
                return f"Moved '{path}' to '{destination}'."

            else:
                return f"Error: unknown action '{action}'. Use: read, write, list, info, delete, copy, move."

        except FileNotFoundError:
            return f"Error: path not found: '{path}'"
        except PermissionError as e:
            return f"Error: permission denied — {e}"
        except Exception as e:
            return f"Error: {e}"
