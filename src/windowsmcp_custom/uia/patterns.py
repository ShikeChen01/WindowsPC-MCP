"""UIAutomation pattern helpers (ElementFromPoint, InvokePattern, ValuePattern, etc.)."""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# UIAutomation pattern IDs
UIA_InvokePatternId = 10000
UIA_ValuePatternId = 10002


def _get_uia():
    """Return the IUIAutomation interface from the module singleton."""
    from .core import get_automation_client
    return get_automation_client().uia


# ---------------------------------------------------------------------------
# Element retrieval
# ---------------------------------------------------------------------------


def get_element_from_point(x: int, y: int):
    """Return the UI Automation element at screen coordinates (*x*, *y*).

    Returns None if UIAutomation is unavailable or the call fails.
    """
    import ctypes

    uia = _get_uia()
    if uia is None:
        return None
    try:
        class _POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        point = _POINT(x, y)
        return uia.ElementFromPoint(point)
    except Exception as exc:
        log.debug("get_element_from_point(%d, %d) failed: %s", x, y, exc)
        return None


def get_element_from_handle(hwnd: int):
    """Return the UI Automation element for the given window handle.

    Returns None if UIAutomation is unavailable or the call fails.
    """
    uia = _get_uia()
    if uia is None:
        return None
    try:
        return uia.ElementFromHandle(hwnd)
    except Exception as exc:
        log.debug("get_element_from_handle(%d) failed: %s", hwnd, exc)
        return None


# ---------------------------------------------------------------------------
# Element property helpers
# ---------------------------------------------------------------------------


def get_element_rect(element) -> tuple[int, int, int, int] | None:
    """Return (left, top, right, bottom) of *element*'s bounding rectangle.

    Returns None if the element is None or the property is unavailable.
    """
    if element is None:
        return None
    try:
        rect = element.CurrentBoundingRectangle
        return (rect.left, rect.top, rect.right, rect.bottom)
    except Exception as exc:
        log.debug("get_element_rect failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Pattern helpers
# ---------------------------------------------------------------------------


def try_invoke(element) -> bool:
    """Try to invoke *element* via InvokePattern (pattern ID 10000).

    Returns True on success, False otherwise.
    """
    if element is None:
        return False
    try:
        pattern = element.GetCurrentPattern(UIA_InvokePatternId)
        if pattern is None:
            return False
        pattern.QueryInterface(type(pattern)).Invoke()
        return True
    except Exception as exc:
        log.debug("try_invoke failed: %s", exc)
        return False


def try_set_value(element, value: str) -> bool:
    """Try to set the value of *element* via ValuePattern (pattern ID 10002).

    Returns True on success, False otherwise.
    """
    if element is None:
        return False
    try:
        pattern = element.GetCurrentPattern(UIA_ValuePatternId)
        if pattern is None:
            return False
        pattern.QueryInterface(type(pattern)).SetValue(value)
        return True
    except Exception as exc:
        log.debug("try_set_value failed: %s", exc)
        return False
