"""UI tree extraction service — walks UIAutomation tree to discover interactive elements."""

from __future__ import annotations

import logging
import ctypes
import ctypes.wintypes as wintypes
from dataclasses import dataclass

from windowsmcp_custom.tree.views import (
    BoundingBox, TreeElementNode, ScrollElementNode, TreeState,
)
from windowsmcp_custom.tree.config import (
    INTERACTIVE_CONTROL_TYPE_NAMES, DOCUMENT_CONTROL_TYPE_NAMES, INTERACTIVE_ROLES,
)
from windowsmcp_custom.uia.core import _AutomationClient

logger = logging.getLogger(__name__)

# UIA property IDs
UIA_NamePropertyId = 30005
UIA_ControlTypePropertyId = 30003
UIA_LocalizedControlTypePropertyId = 30004
UIA_BoundingRectanglePropertyId = 30001
UIA_IsEnabledPropertyId = 30010
UIA_IsOffscreenPropertyId = 30022
UIA_IsControlElementPropertyId = 30016
UIA_HasKeyboardFocusPropertyId = 30008
UIA_IsKeyboardFocusablePropertyId = 30009
UIA_IsPasswordPropertyId = 30019
UIA_LegacyIAccessibleRolePropertyId = 30095
UIA_LegacyIAccessibleValuePropertyId = 30093
UIA_LegacyIAccessibleDefaultActionPropertyId = 30100
UIA_AcceleratorKeyPropertyId = 30006
UIA_HelpTextPropertyId = 30013
UIA_ToggleToggleStatePropertyId = 30086
UIA_ScrollPatternId = 10004
UIA_ScrollVerticallyScrollablePropertyId = 30057
UIA_ScrollVerticalScrollPercentPropertyId = 30053
UIA_ScrollHorizontallyScrollablePropertyId = 30056
UIA_ScrollHorizontalScrollPercentPropertyId = 30052

# Control type IDs from UIA
_CONTROL_TYPE_NAMES = {
    50000: "ButtonControl", 50001: "CalendarControl", 50002: "CheckBoxControl",
    50003: "ComboBoxControl", 50004: "EditControl", 50005: "HyperlinkControl",
    50006: "ImageControl", 50007: "ListItemControl", 50008: "ListControl",
    50009: "MenuControl", 50010: "MenuBarControl", 50011: "MenuItemControl",
    50012: "ProgressBarControl", 50013: "RadioButtonControl", 50014: "ScrollBarControl",
    50015: "SliderControl", 50016: "SpinnerControl", 50017: "StatusBarControl",
    50018: "TabControl", 50019: "TabItemControl", 50020: "TextControl",
    50021: "ToolBarControl", 50022: "ToolTipControl", 50023: "TreeControl",
    50024: "TreeItemControl", 50025: "CustomControl", 50026: "GroupControl",
    50027: "ThumbControl", 50028: "DataGridControl", 50029: "DataItemControl",
    50030: "DocumentControl", 50031: "SplitButtonControl", 50032: "WindowControl",
    50033: "PaneControl", 50034: "HeaderControl", 50035: "HeaderItemControl",
    50036: "TableControl", 50037: "TitleBarControl", 50038: "SeparatorControl",
}

# Accessibility role names
_ROLE_NAMES = {
    0: "Default", 9: "PushButton", 10: "CheckButton", 12: "RadioButton",
    11: "ComboBox", 13: "DropList", 30: "Link", 29: "Text", 33: "List",
    34: "ListItem", 35: "Outline", 36: "OutlineItem",
    37: "PageTab", 38: "PropertyPage", 39: "Indicator", 40: "Graphic",
    41: "StaticText", 42: "EditableText", 43: "PushButton", 44: "CheckButton",
    45: "RadioButton", 48: "SpinButton", 51: "Slider", 52: "Dial",
    55: "MenuItem", 56: "Column", 57: "Row", 58: "ColumnHeader",
    59: "RowHeader", 60: "Cell", 61: "Link", 62: "ScrollBar",
    63: "Grip", 64: "Cursor", 46: "DropList", 47: "Clock",
    54: "SplitButton",
}


class TreeService:
    """Walks the UIAutomation tree to extract interactive and scrollable elements.

    Scoped to a specific screen region (agent display bounds) for confinement.
    """

    def __init__(self, screen_bounds: BoundingBox):
        self._screen_bounds = screen_bounds
        self._client = None

    def _get_client(self):
        if self._client is None:
            self._client = _AutomationClient()
        return self._client

    def get_state(self, window_handles: list[int] | None = None) -> TreeState:
        """Extract the UI tree for windows on the agent screen.

        Args:
            window_handles: Specific window handles to scan. If None, scans all
                           visible windows whose center is on the agent screen.

        Returns:
            TreeState with interactive and scrollable elements.
        """
        interactive_nodes: list[TreeElementNode] = []
        scrollable_nodes: list[ScrollElementNode] = []

        if window_handles is None:
            window_handles = self._get_windows_on_screen()

        for hwnd in window_handles:
            try:
                self._extract_from_window(hwnd, interactive_nodes, scrollable_nodes)
            except Exception:
                logger.debug(f"Failed to extract tree from window {hwnd}", exc_info=True)

        return TreeState(
            interactive_nodes=interactive_nodes,
            scrollable_nodes=scrollable_nodes,
        )

    def _get_windows_on_screen(self) -> list[int]:
        """Get handles of all visible windows whose center is on the agent screen."""
        from windowsmcp_custom.uia.controls import (
            enumerate_windows, get_window_rect, is_window_visible, get_window_title,
        )
        handles = []
        for hwnd in enumerate_windows():
            if not is_window_visible(hwnd):
                continue
            rect = get_window_rect(hwnd)
            if rect is None:
                continue
            title = get_window_title(hwnd)
            if not title:
                continue
            cx = (rect[0] + rect[2]) // 2
            cy = (rect[1] + rect[3]) // 2
            if self._screen_bounds.contains_point(cx, cy):
                handles.append(hwnd)
        return handles

    def _extract_from_window(
        self, hwnd: int,
        interactive_nodes: list[TreeElementNode],
        scrollable_nodes: list[ScrollElementNode],
    ):
        """Extract interactive/scrollable elements from a single window."""
        from windowsmcp_custom.uia.controls import get_window_title, get_window_rect

        client = self._get_client()
        if client.uia is None:
            return

        title = get_window_title(hwnd)
        rect = get_window_rect(hwnd)
        if not rect or not title:
            return

        window_box = BoundingBox(left=rect[0], top=rect[1], right=rect[2], bottom=rect[3])

        try:
            element = client.uia.ElementFromHandle(hwnd)
            if element is None:
                return
            self._traverse(element, window_box, title, interactive_nodes, scrollable_nodes, depth=0)
        except Exception:
            logger.debug(f"UIA traversal failed for '{title}'", exc_info=True)

    def _traverse(
        self,
        element,
        window_box: BoundingBox,
        window_name: str,
        interactive_nodes: list[TreeElementNode],
        scrollable_nodes: list[ScrollElementNode],
        depth: int,
    ):
        """DFS traversal of the UIAutomation tree."""
        if depth > 25:  # Prevent infinite recursion
            return

        try:
            # Get control type
            ct_id = element.GetCurrentPropertyValue(UIA_ControlTypePropertyId)
            control_type_name = _CONTROL_TYPE_NAMES.get(ct_id, "UnknownControl")

            # Get bounding rectangle
            rect = element.CurrentBoundingRectangle
            elem_box = BoundingBox(left=rect.left, top=rect.top, right=rect.right, bottom=rect.bottom)

            # Visibility checks
            is_offscreen = element.GetCurrentPropertyValue(UIA_IsOffscreenPropertyId)
            is_enabled = element.GetCurrentPropertyValue(UIA_IsEnabledPropertyId)
            is_control = element.GetCurrentPropertyValue(UIA_IsControlElementPropertyId)

            if not elem_box.is_valid() or is_offscreen or not is_control:
                # Still traverse children — they might be visible
                pass
            elif is_enabled:
                # Clip to window and screen bounds
                clipped = elem_box.intersect(window_box).intersect(self._screen_bounds)
                if clipped.is_valid():
                    self._classify_element(
                        element, control_type_name, clipped, window_name,
                        interactive_nodes, scrollable_nodes,
                    )

        except Exception:
            pass  # Individual element failure shouldn't stop traversal

        # Traverse children
        try:
            client = self._get_client()
            walker = client.walker
            if walker is None:
                return
            child = walker.GetFirstChildElement(element)
            while child is not None:
                self._traverse(child, window_box, window_name, interactive_nodes, scrollable_nodes, depth + 1)
                child = walker.GetNextSiblingElement(child)
        except Exception:
            pass

    def _classify_element(
        self,
        element,
        control_type_name: str,
        clipped_box: BoundingBox,
        window_name: str,
        interactive_nodes: list[TreeElementNode],
        scrollable_nodes: list[ScrollElementNode],
    ):
        """Classify an element as interactive, scrollable, or neither."""
        # Check for scrollable
        try:
            v_scrollable = element.GetCurrentPropertyValue(UIA_ScrollVerticallyScrollablePropertyId)
            h_scrollable = element.GetCurrentPropertyValue(UIA_ScrollHorizontallyScrollablePropertyId)
            if v_scrollable or h_scrollable:
                name = self._get_name(element) or control_type_name
                v_percent = element.GetCurrentPropertyValue(UIA_ScrollVerticalScrollPercentPropertyId) or 0
                h_percent = element.GetCurrentPropertyValue(UIA_ScrollHorizontalScrollPercentPropertyId) or 0
                scrollable_nodes.append(ScrollElementNode(
                    name=name,
                    control_type=control_type_name.replace("Control", ""),
                    bounding_box=clipped_box,
                    window_name=window_name,
                    metadata={
                        "vertical_scrollable": bool(v_scrollable),
                        "vertical_scroll_percent": round(float(v_percent), 1) if v_percent and v_percent >= 0 else 0,
                        "horizontal_scrollable": bool(h_scrollable),
                        "horizontal_scroll_percent": round(float(h_percent), 1) if h_percent and h_percent >= 0 else 0,
                    },
                ))
        except Exception:
            pass

        # Check for interactive
        if control_type_name in INTERACTIVE_CONTROL_TYPE_NAMES or control_type_name in DOCUMENT_CONTROL_TYPE_NAMES:
            # Verify via accessibility role
            try:
                role_id = element.GetCurrentPropertyValue(UIA_LegacyIAccessibleRolePropertyId) or 0
                role_name = _ROLE_NAMES.get(role_id, "Default")
                if role_name not in INTERACTIVE_ROLES and control_type_name not in {"EditControl", "ComboBoxControl"}:
                    return  # Not truly interactive
            except Exception:
                pass  # If we can't get the role, assume interactive based on control type

            name = self._get_name(element) or ""
            metadata = self._extract_metadata(element, control_type_name)

            interactive_nodes.append(TreeElementNode(
                name=name,
                control_type=control_type_name.replace("Control", ""),
                bounding_box=clipped_box,
                window_name=window_name,
                metadata=metadata,
            ))

    def _get_name(self, element) -> str:
        """Get the element's name, handling errors."""
        try:
            name = element.GetCurrentPropertyValue(UIA_NamePropertyId)
            return (name or "").strip()
        except Exception:
            return ""

    def _extract_metadata(self, element, control_type_name: str) -> dict:
        """Extract control-specific metadata."""
        metadata = {}
        try:
            focused = element.GetCurrentPropertyValue(UIA_HasKeyboardFocusPropertyId)
            metadata["has_focused"] = bool(focused)
        except Exception:
            metadata["has_focused"] = False

        try:
            accel = element.GetCurrentPropertyValue(UIA_AcceleratorKeyPropertyId)
            if accel:
                metadata["shortcut"] = accel
        except Exception:
            pass

        try:
            help_text = element.GetCurrentPropertyValue(UIA_HelpTextPropertyId)
            if help_text:
                metadata["help_text"] = help_text[:100]  # Truncate
        except Exception:
            pass

        # EditControl: get current value
        if control_type_name == "EditControl":
            try:
                value = element.GetCurrentPropertyValue(UIA_LegacyIAccessibleValuePropertyId)
                metadata["value"] = (value or "").strip()[:200]
                is_pw = element.GetCurrentPropertyValue(UIA_IsPasswordPropertyId)
                if is_pw:
                    metadata["is_password"] = True
            except Exception:
                pass

        # Button/CheckBox: toggle state
        if control_type_name in ("ButtonControl", "CheckBoxControl"):
            try:
                toggle = element.GetCurrentPropertyValue(UIA_ToggleToggleStatePropertyId)
                if toggle == 1:
                    metadata["toggle_state"] = "on"
                elif toggle == 0:
                    metadata["toggle_state"] = "off"
            except Exception:
                pass

        return metadata
