"""Typed exceptions for the confinement subsystem."""


class WindowsMCPError(Exception):
    """Base for all WindowsMCP errors."""
    pass


class ConfinementError(WindowsMCPError):
    """Coordinates are outside agent screen bounds."""
    pass


class InvalidStateError(WindowsMCPError):
    """Server is not in the right state for this operation."""
    pass


class BlockedShortcutError(WindowsMCPError):
    """Shortcut is on the blocked list."""
    pass


class DisplayUnavailableError(WindowsMCPError):
    """Agent display is not active or accessible."""
    pass


class TargetNotFoundError(WindowsMCPError):
    """UI element or window could not be found."""
    pass


class AgentPreempted(WindowsMCPError):
    """Human has taken control. Agent should wait for resume."""
    pass


class AgentPaused(WindowsMCPError):
    """Agent is paused. User's desktop is active."""
    pass


class EmergencyStop(WindowsMCPError):
    """Session terminated by user. No recovery."""
    pass
