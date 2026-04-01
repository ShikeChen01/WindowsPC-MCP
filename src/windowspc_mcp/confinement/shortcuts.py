"""Shortcut allowlist/blocklist for confinement engine."""

from __future__ import annotations

# Canonical modifier ordering: ctrl / alt / shift / win, then key(s)
_MODIFIER_ORDER = ["ctrl", "alt", "shift", "win"]


def normalize_shortcut(shortcut: str) -> str:
    """Normalize a shortcut string to lowercase with consistent modifier ordering.

    Modifier order: ctrl, alt, shift, win, then remaining keys in original order.
    """
    parts = [p.strip().lower() for p in shortcut.split("+")]
    modifiers = [p for p in parts if p in _MODIFIER_ORDER]
    keys = [p for p in parts if p not in _MODIFIER_ORDER]

    # Sort modifiers by canonical order
    modifiers.sort(key=lambda m: _MODIFIER_ORDER.index(m))

    return "+".join(modifiers + keys)


BLOCKED_SHORTCUTS: frozenset[str] = frozenset(
    normalize_shortcut(s) for s in {
        "win+d",
        "win+tab",
        "win+l",
        "win+r",
        "win+e",
        "win+m",
        "win+shift+m",
        "alt+tab",
        "alt+shift+tab",
        "alt+f4",
        "ctrl+alt+del",
        "ctrl+shift+esc",
        "win+ctrl+d",
        "win+ctrl+left",
        "win+ctrl+right",
        "win+ctrl+f4",
    }
)

ALLOWED_SHORTCUTS: frozenset[str] = frozenset({
    # ctrl + letter
    "ctrl+c",
    "ctrl+x",
    "ctrl+v",
    "ctrl+z",
    "ctrl+y",
    "ctrl+a",
    "ctrl+s",
    "ctrl+f",
    "ctrl+p",
    "ctrl+n",
    "ctrl+w",
    "ctrl+t",
    # ctrl + shift + letter
    "ctrl+shift+t",
    "ctrl+shift+n",
    # tab navigation
    "ctrl+tab",
    "ctrl+shift+tab",
    # function keys
    "f1",
    "f2",
    "f3",
    "f4",
    "f5",
    "f6",
    "f7",
    "f8",
    "f9",
    "f10",
    "f11",
    "f12",
    # special keys
    "enter",
    "escape",
    "tab",
    "backspace",
    "delete",
    "home",
    "end",
    "pageup",
    "pagedown",
    # arrow keys
    "up",
    "down",
    "left",
    "right",
    # shift+tab
    "shift+tab",
})

# Reasons dict with normalized keys so lookups always match BLOCKED_SHORTCUTS
_REASONS: dict[str, str] = {
    normalize_shortcut(k): v for k, v in {
        "win+d": "shows/hides the desktop, disrupting the agent's workspace",
        "win+tab": "opens Task View / virtual desktop switcher",
        "win+l": "locks the workstation session",
        "win+r": "opens the Run dialog",
        "win+e": "opens File Explorer",
        "win+m": "minimises all windows",
        "win+shift+m": "restores all minimised windows",
        "alt+tab": "switches the active application focus",
        "alt+shift+tab": "switches the active application focus in reverse",
        "alt+f4": "closes the active window or application",
        "ctrl+alt+del": "opens the Windows security screen",
        "ctrl+shift+esc": "opens Task Manager",
        "win+ctrl+d": "creates a new virtual desktop",
        "win+ctrl+left": "switches to the previous virtual desktop",
        "win+ctrl+right": "switches to the next virtual desktop",
        "win+ctrl+f4": "closes the current virtual desktop",
    }.items()
}


def is_shortcut_allowed(shortcut: str) -> bool:
    """Return True if the shortcut is permitted for an agent to use.

    Logic:
      1. If it is in BLOCKED_SHORTCUTS -> deny.
      2. If it is in ALLOWED_SHORTCUTS -> allow.
      3. If it contains the 'win' modifier -> deny (safety default).
      4. Otherwise -> allow.
    """
    normalized = normalize_shortcut(shortcut)

    if normalized in BLOCKED_SHORTCUTS:
        return False

    if normalized in ALLOWED_SHORTCUTS:
        return True

    # Block any shortcut with the win modifier not explicitly allowed
    parts = normalized.split("+")
    if "win" in parts:
        return False

    return True


def get_blocked_reason(shortcut: str) -> str:
    """Return a human-readable reason why a shortcut is blocked."""
    normalized = normalize_shortcut(shortcut)

    if normalized in BLOCKED_SHORTCUTS:
        return _REASONS.get(normalized, "this shortcut is on the blocked list")

    parts = normalized.split("+")
    if "win" in parts:
        return "shortcuts with the Win modifier are blocked by default unless explicitly allowed"

    return f"'{shortcut}' is not permitted"
