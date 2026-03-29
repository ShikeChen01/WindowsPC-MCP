"""Process tool: list and kill processes."""

from __future__ import annotations

from typing import Optional

from windowspc_mcp.confinement.decorators import guarded_tool, with_tool_name


def register(mcp, *, get_display_manager, get_confinement, get_state_manager=None, get_guard=None, get_input_service=None):
    """Register the Process tool."""

    @mcp.tool(
        name="Process",
        description=(
            "Manage running processes. "
            "action: 'list' (default) — list processes, optionally filtered by name; "
            "'kill' — terminate by name or pid."
        ),
    )
    @guarded_tool(get_guard)
    @with_tool_name("Process")
    def process(
        action: str = "list",
        name: Optional[str] = None,
        pid: Optional[int] = None,
    ) -> str:
        import psutil

        action = action.lower().strip()

        try:
            if action == "list":
                procs = []
                for proc in psutil.process_iter(["pid", "name", "status", "memory_info"]):
                    try:
                        info = proc.info
                        if name and name.lower() not in (info["name"] or "").lower():
                            continue
                        mem_mb = (
                            info["memory_info"].rss / (1024 * 1024)
                            if info.get("memory_info")
                            else 0.0
                        )
                        procs.append(
                            f"PID {info['pid']:6d}  {info['status']:10s}  {mem_mb:7.1f}MB  {info['name']}"
                        )
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue

                if not procs:
                    return "No matching processes found."
                header = f"{'PID':>6}  {'STATUS':<10}  {'MEMORY':>8}  NAME\n" + "-" * 50
                return header + "\n" + "\n".join(procs[:200])

            elif action == "kill":
                if pid is None and name is None:
                    return "Error: provide 'pid' or 'name' to kill."

                killed = []
                errors = []

                if pid is not None:
                    try:
                        proc = psutil.Process(pid)
                        proc_name = proc.name()
                        proc.terminate()
                        killed.append(f"PID {pid} ({proc_name})")
                    except psutil.NoSuchProcess:
                        return f"Error: no process with PID {pid}."
                    except psutil.AccessDenied:
                        return f"Error: access denied when killing PID {pid}."
                    except Exception as e:
                        return f"Error killing PID {pid}: {e}"
                else:
                    for proc in psutil.process_iter(["pid", "name"]):
                        try:
                            if name.lower() in (proc.info["name"] or "").lower():
                                proc.terminate()
                                killed.append(f"PID {proc.info['pid']} ({proc.info['name']})")
                        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                            errors.append(str(e))

                if not killed and not errors:
                    return f"No processes matching name '{name}' found."

                result = f"Terminated: {', '.join(killed)}." if killed else "No processes terminated."
                if errors:
                    result += f" Errors: {'; '.join(errors)}"
                return result

            else:
                return f"Error: unknown action '{action}'. Use 'list' or 'kill'."

        except Exception as e:
            return f"Error: {e}"
