"""Registry tool: read, write, and list Windows registry keys."""

from __future__ import annotations

from typing import Optional

from windowsmcp_custom.confinement.decorators import guarded_tool, with_tool_name


# Map hive name strings to winreg constants
_HIVE_MAP = {
    "HKLM": "HKEY_LOCAL_MACHINE",
    "HKEY_LOCAL_MACHINE": "HKEY_LOCAL_MACHINE",
    "HKCU": "HKEY_CURRENT_USER",
    "HKEY_CURRENT_USER": "HKEY_CURRENT_USER",
    "HKCR": "HKEY_CLASSES_ROOT",
    "HKEY_CLASSES_ROOT": "HKEY_CLASSES_ROOT",
    "HKU": "HKEY_USERS",
    "HKEY_USERS": "HKEY_USERS",
    "HKCC": "HKEY_CURRENT_CONFIG",
    "HKEY_CURRENT_CONFIG": "HKEY_CURRENT_CONFIG",
}

_VALUE_TYPE_MAP = {
    "REG_SZ": None,           # resolved at runtime
    "REG_DWORD": None,
    "REG_QWORD": None,
    "REG_BINARY": None,
    "REG_EXPAND_SZ": None,
    "REG_MULTI_SZ": None,
}


def _parse_key(key: str):
    """Parse 'HKLM\\path\\to\\key' into (hive_handle, subkey_path)."""
    import winreg

    hive_const_map = {
        "HKEY_LOCAL_MACHINE": winreg.HKEY_LOCAL_MACHINE,
        "HKEY_CURRENT_USER": winreg.HKEY_CURRENT_USER,
        "HKEY_CLASSES_ROOT": winreg.HKEY_CLASSES_ROOT,
        "HKEY_USERS": winreg.HKEY_USERS,
        "HKEY_CURRENT_CONFIG": winreg.HKEY_CURRENT_CONFIG,
    }

    parts = key.replace("/", "\\").split("\\", 1)
    hive_str = parts[0].upper()
    subkey = parts[1] if len(parts) > 1 else ""

    canonical = _HIVE_MAP.get(hive_str)
    if canonical is None:
        raise ValueError(f"Unknown registry hive: '{hive_str}'. Use HKLM, HKCU, etc.")

    hive = hive_const_map[canonical]
    return hive, subkey


def register(mcp, *, get_display_manager, get_confinement, get_state_manager=None, get_guard=None, get_input_service=None):
    """Register the Registry tool."""

    @mcp.tool(
        name="Registry",
        description=(
            "Read, write, or list Windows registry values. "
            "action: 'read', 'write', 'list'. "
            "key: registry path like 'HKLM\\\\SOFTWARE\\\\MyApp' or 'HKCU\\\\path'. "
            "name: value name (for read/write). "
            "value: data to write (for write). "
            "value_type: REG_SZ (default), REG_DWORD, REG_QWORD, REG_BINARY, REG_EXPAND_SZ, REG_MULTI_SZ."
        ),
    )
    @guarded_tool(get_guard)
    @with_tool_name("Registry")
    def registry(
        action: str,
        key: str,
        name: Optional[str] = None,
        value: Optional[str] = None,
        value_type: str = "REG_SZ",
    ) -> str:
        import winreg

        action = action.lower().strip()

        type_map = {
            "REG_SZ": winreg.REG_SZ,
            "REG_DWORD": winreg.REG_DWORD,
            "REG_QWORD": winreg.REG_QWORD,
            "REG_BINARY": winreg.REG_BINARY,
            "REG_EXPAND_SZ": winreg.REG_EXPAND_SZ,
            "REG_MULTI_SZ": winreg.REG_MULTI_SZ,
        }

        try:
            hive, subkey = _parse_key(key)
        except ValueError as e:
            return f"Error: {e}"

        try:
            if action == "read":
                if name is None:
                    return "Error: 'name' is required for read."
                with winreg.OpenKey(hive, subkey, access=winreg.KEY_READ) as k:
                    data, reg_type = winreg.QueryValueEx(k, name)
                    type_name = next((n for n, v in type_map.items() if v == reg_type), str(reg_type))
                    return f"{name} ({type_name}) = {data!r}"

            elif action == "write":
                if name is None:
                    return "Error: 'name' is required for write."
                if value is None:
                    return "Error: 'value' is required for write."

                reg_type = type_map.get(value_type.upper())
                if reg_type is None:
                    return f"Error: unknown value_type '{value_type}'."

                # Coerce value to the appropriate Python type
                if reg_type == winreg.REG_DWORD:
                    coerced = int(value)
                elif reg_type == winreg.REG_QWORD:
                    coerced = int(value)
                elif reg_type == winreg.REG_BINARY:
                    coerced = bytes.fromhex(value)
                elif reg_type == winreg.REG_MULTI_SZ:
                    # Expect pipe-separated values
                    coerced = value.split("|")
                else:
                    coerced = value

                with winreg.OpenKey(
                    hive, subkey, access=winreg.KEY_SET_VALUE | winreg.KEY_CREATE_SUB_KEY
                ) as k:
                    winreg.SetValueEx(k, name, 0, reg_type, coerced)
                return f"Written '{name}' = {coerced!r} ({value_type}) to '{key}'."

            elif action == "list":
                with winreg.OpenKey(hive, subkey, access=winreg.KEY_READ) as k:
                    lines = []
                    # List subkeys
                    i = 0
                    while True:
                        try:
                            subkey_name = winreg.EnumKey(k, i)
                            lines.append(f"[key] {subkey_name}\\")
                            i += 1
                        except OSError:
                            break
                    # List values
                    i = 0
                    while True:
                        try:
                            vname, vdata, vtype = winreg.EnumValue(k, i)
                            type_name = next(
                                (n for n, v in type_map.items() if v == vtype), str(vtype)
                            )
                            lines.append(f"[{type_name}] {vname!r} = {vdata!r}")
                            i += 1
                        except OSError:
                            break
                    return "\n".join(lines) if lines else "(empty key)"

            else:
                return f"Error: unknown action '{action}'. Use 'read', 'write', or 'list'."

        except FileNotFoundError:
            return f"Error: registry key not found: '{key}'"
        except PermissionError as e:
            return f"Error: permission denied — {e}"
        except Exception as e:
            return f"Error: {e}"
