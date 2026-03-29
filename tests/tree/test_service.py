"""Tests for windowspc_mcp.tree.service — TreeService UI tree extraction."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock
import pytest

from windowspc_mcp.tree.views import BoundingBox, TreeElementNode, ScrollElementNode, TreeState
from windowspc_mcp.tree.service import (
    TreeService,
    _CONTROL_TYPE_NAMES,
    _ROLE_NAMES,
    UIA_ControlTypePropertyId,
    UIA_BoundingRectanglePropertyId,
    UIA_IsOffscreenPropertyId,
    UIA_IsEnabledPropertyId,
    UIA_IsControlElementPropertyId,
    UIA_NamePropertyId,
    UIA_ScrollVerticallyScrollablePropertyId,
    UIA_ScrollHorizontallyScrollablePropertyId,
    UIA_ScrollVerticalScrollPercentPropertyId,
    UIA_ScrollHorizontalScrollPercentPropertyId,
    UIA_LegacyIAccessibleRolePropertyId,
    UIA_HasKeyboardFocusPropertyId,
    UIA_AcceleratorKeyPropertyId,
    UIA_HelpTextPropertyId,
    UIA_LegacyIAccessibleValuePropertyId,
    UIA_IsPasswordPropertyId,
    UIA_ToggleToggleStatePropertyId,
)
from windowspc_mcp.tree.config import INTERACTIVE_CONTROL_TYPE_NAMES


# ── Helpers ──────────────────────────────────────────────────────────────────

SCREEN = BoundingBox(left=0, top=0, right=1920, bottom=1080)


def _make_service(screen: BoundingBox | None = None) -> TreeService:
    """Create a TreeService with a mock client pre-injected."""
    svc = TreeService(screen or SCREEN)
    mock_client = MagicMock()
    mock_client.uia = MagicMock()
    mock_client.walker = MagicMock()
    svc._client = mock_client
    return svc


def _make_rect(left=10, top=10, right=200, bottom=50):
    """Return a mock rect object matching UIAutomation CurrentBoundingRectangle."""
    return SimpleNamespace(left=left, top=top, right=right, bottom=bottom)


def _make_element(
    control_type_id: int = 50000,  # ButtonControl
    name: str = "OK",
    rect=None,
    is_offscreen: bool = False,
    is_enabled: bool = True,
    is_control: bool = True,
    role_id: int = 9,  # PushButton
    has_focus: bool = False,
    accel_key: str = "",
    help_text: str = "",
    value: str = "",
    is_password: bool = False,
    toggle_state=None,
    v_scrollable: bool = False,
    h_scrollable: bool = False,
    v_scroll_pct: float = 0,
    h_scroll_pct: float = 0,
):
    """Build a mock UIA element with configurable property values."""
    if rect is None:
        rect = _make_rect()
    element = MagicMock()
    element.CurrentBoundingRectangle = rect

    def prop_value(prop_id):
        mapping = {
            UIA_ControlTypePropertyId: control_type_id,
            UIA_IsOffscreenPropertyId: is_offscreen,
            UIA_IsEnabledPropertyId: is_enabled,
            UIA_IsControlElementPropertyId: is_control,
            UIA_NamePropertyId: name,
            UIA_LegacyIAccessibleRolePropertyId: role_id,
            UIA_HasKeyboardFocusPropertyId: has_focus,
            UIA_AcceleratorKeyPropertyId: accel_key,
            UIA_HelpTextPropertyId: help_text,
            UIA_LegacyIAccessibleValuePropertyId: value,
            UIA_IsPasswordPropertyId: is_password,
            UIA_ToggleToggleStatePropertyId: toggle_state,
            UIA_ScrollVerticallyScrollablePropertyId: v_scrollable,
            UIA_ScrollHorizontallyScrollablePropertyId: h_scrollable,
            UIA_ScrollVerticalScrollPercentPropertyId: v_scroll_pct,
            UIA_ScrollHorizontalScrollPercentPropertyId: h_scroll_pct,
        }
        return mapping.get(prop_id, None)

    element.GetCurrentPropertyValue = MagicMock(side_effect=prop_value)
    return element


def _setup_walker_no_children(svc: TreeService):
    """Configure the walker mock to report no children for any element."""
    svc._client.walker.GetFirstChildElement.return_value = None


def _setup_walker_with_children(svc: TreeService, parent_element, children: list):
    """Configure the walker to return a list of children for a given parent."""
    walker = svc._client.walker
    # GetFirstChildElement returns first child when called with parent
    if children:
        walker.GetFirstChildElement.side_effect = lambda el: (
            children[0] if el is parent_element else None
        )
        # Chain siblings
        for i, child in enumerate(children):
            next_sibling = children[i + 1] if i + 1 < len(children) else None
            walker.GetNextSiblingElement.side_effect = (
                lambda el, _children=children: (
                    _children[_children.index(el) + 1]
                    if el in _children and _children.index(el) + 1 < len(_children)
                    else None
                )
            )
    else:
        walker.GetFirstChildElement.return_value = None


# ── Control type / role name dictionaries ────────────────────────────────────

class TestControlTypeNames:
    def test_button_control_id(self):
        assert _CONTROL_TYPE_NAMES[50000] == "ButtonControl"

    def test_edit_control_id(self):
        assert _CONTROL_TYPE_NAMES[50004] == "EditControl"

    def test_window_control_id(self):
        assert _CONTROL_TYPE_NAMES[50032] == "WindowControl"

    def test_unknown_id_returns_default(self):
        assert _CONTROL_TYPE_NAMES.get(99999, "UnknownControl") == "UnknownControl"

    def test_all_ids_in_range(self):
        for key in _CONTROL_TYPE_NAMES:
            assert 50000 <= key <= 50038


class TestRoleNames:
    def test_push_button(self):
        assert _ROLE_NAMES[9] == "PushButton"

    def test_default_role(self):
        assert _ROLE_NAMES[0] == "Default"

    def test_link(self):
        assert _ROLE_NAMES[30] == "Link"

    def test_unknown_role_get(self):
        assert _ROLE_NAMES.get(9999, "Default") == "Default"


# ── TreeService.__init__ / _get_client ───────────────────────────────────────

class TestTreeServiceInit:
    def test_stores_screen_bounds(self):
        svc = TreeService(SCREEN)
        assert svc._screen_bounds is SCREEN

    def test_client_initially_none(self):
        svc = TreeService(SCREEN)
        assert svc._client is None

    @patch("windowspc_mcp.tree.service._AutomationClient")
    def test_get_client_creates_once(self, MockClient):
        svc = TreeService(SCREEN)
        svc._client = None
        c1 = svc._get_client()
        c2 = svc._get_client()
        assert c1 is c2
        MockClient.assert_called_once()


# ── get_state ────────────────────────────────────────────────────────────────

class TestGetState:
    def test_returns_tree_state(self):
        svc = _make_service()
        _setup_walker_no_children(svc)
        result = svc.get_state(window_handles=[])
        assert isinstance(result, TreeState)
        assert result.interactive_nodes == []
        assert result.scrollable_nodes == []

    @patch("windowspc_mcp.tree.service.TreeService._get_windows_on_screen")
    def test_auto_discovers_windows_when_handles_none(self, mock_get_win):
        mock_get_win.return_value = []
        svc = _make_service()
        svc.get_state(window_handles=None)
        mock_get_win.assert_called_once()

    def test_explicit_handles_skip_autodiscovery(self):
        svc = _make_service()
        _setup_walker_no_children(svc)
        with patch.object(svc, "_get_windows_on_screen") as mock_gw:
            svc.get_state(window_handles=[12345])
            mock_gw.assert_not_called()

    @patch("windowspc_mcp.tree.service.TreeService._extract_from_window")
    def test_exception_in_one_window_does_not_stop_others(self, mock_extract):
        mock_extract.side_effect = [RuntimeError("boom"), None]
        svc = _make_service()
        result = svc.get_state(window_handles=[1, 2])
        assert mock_extract.call_count == 2
        assert isinstance(result, TreeState)


# ── _get_windows_on_screen ───────────────────────────────────────────────────

class TestGetWindowsOnScreen:
    @patch("windowspc_mcp.uia.controls.get_window_title", return_value="Notepad")
    @patch("windowspc_mcp.uia.controls.get_window_rect", return_value=(100, 100, 300, 300))
    @patch("windowspc_mcp.uia.controls.is_window_visible", return_value=True)
    @patch("windowspc_mcp.uia.controls.enumerate_windows", return_value=[111])
    def test_includes_visible_window_on_screen(self, *mocks):
        svc = _make_service()
        handles = svc._get_windows_on_screen()
        assert 111 in handles

    @patch("windowspc_mcp.uia.controls.get_window_title", return_value="App")
    @patch("windowspc_mcp.uia.controls.get_window_rect", return_value=(100, 100, 300, 300))
    @patch("windowspc_mcp.uia.controls.is_window_visible", return_value=False)
    @patch("windowspc_mcp.uia.controls.enumerate_windows", return_value=[111])
    def test_excludes_invisible_window(self, *mocks):
        svc = _make_service()
        handles = svc._get_windows_on_screen()
        assert 111 not in handles

    @patch("windowspc_mcp.uia.controls.get_window_title", return_value="App")
    @patch("windowspc_mcp.uia.controls.get_window_rect", return_value=None)
    @patch("windowspc_mcp.uia.controls.is_window_visible", return_value=True)
    @patch("windowspc_mcp.uia.controls.enumerate_windows", return_value=[111])
    def test_excludes_window_with_no_rect(self, *mocks):
        svc = _make_service()
        handles = svc._get_windows_on_screen()
        assert 111 not in handles

    @patch("windowspc_mcp.uia.controls.get_window_title", return_value="")
    @patch("windowspc_mcp.uia.controls.get_window_rect", return_value=(100, 100, 300, 300))
    @patch("windowspc_mcp.uia.controls.is_window_visible", return_value=True)
    @patch("windowspc_mcp.uia.controls.enumerate_windows", return_value=[111])
    def test_excludes_window_with_empty_title(self, *mocks):
        svc = _make_service()
        handles = svc._get_windows_on_screen()
        assert 111 not in handles

    @patch("windowspc_mcp.uia.controls.get_window_title", return_value="App")
    @patch("windowspc_mcp.uia.controls.get_window_rect", return_value=(5000, 5000, 5200, 5200))
    @patch("windowspc_mcp.uia.controls.is_window_visible", return_value=True)
    @patch("windowspc_mcp.uia.controls.enumerate_windows", return_value=[111])
    def test_excludes_window_off_screen(self, *mocks):
        svc = _make_service()
        handles = svc._get_windows_on_screen()
        assert 111 not in handles


# ── _extract_from_window ─────────────────────────────────────────────────────

class TestExtractFromWindow:
    @patch("windowspc_mcp.uia.controls.get_window_rect", return_value=(0, 0, 800, 600))
    @patch("windowspc_mcp.uia.controls.get_window_title", return_value="Notepad")
    def test_calls_traverse(self, mock_title, mock_rect):
        svc = _make_service()
        element = MagicMock()
        svc._client.uia.ElementFromHandle.return_value = element
        _setup_walker_no_children(svc)

        interactive, scrollable = [], []
        with patch.object(svc, "_traverse") as mock_traverse:
            svc._extract_from_window(12345, interactive, scrollable)
            mock_traverse.assert_called_once()

    @patch("windowspc_mcp.uia.controls.get_window_rect", return_value=None)
    @patch("windowspc_mcp.uia.controls.get_window_title", return_value="Notepad")
    def test_returns_early_if_no_rect(self, mock_title, mock_rect):
        svc = _make_service()
        interactive, scrollable = [], []
        svc._extract_from_window(12345, interactive, scrollable)
        svc._client.uia.ElementFromHandle.assert_not_called()

    @patch("windowspc_mcp.uia.controls.get_window_rect", return_value=(0, 0, 800, 600))
    @patch("windowspc_mcp.uia.controls.get_window_title", return_value="")
    def test_returns_early_if_no_title(self, mock_title, mock_rect):
        svc = _make_service()
        interactive, scrollable = [], []
        svc._extract_from_window(12345, interactive, scrollable)
        svc._client.uia.ElementFromHandle.assert_not_called()

    def test_returns_early_if_uia_is_none(self):
        svc = _make_service()
        svc._client.uia = None
        interactive, scrollable = [], []
        svc._extract_from_window(12345, interactive, scrollable)
        # Should not raise

    @patch("windowspc_mcp.uia.controls.get_window_rect", return_value=(0, 0, 800, 600))
    @patch("windowspc_mcp.uia.controls.get_window_title", return_value="App")
    def test_element_from_handle_returns_none(self, mock_title, mock_rect):
        svc = _make_service()
        svc._client.uia.ElementFromHandle.return_value = None
        interactive, scrollable = [], []
        svc._extract_from_window(12345, interactive, scrollable)
        assert interactive == [] and scrollable == []

    @patch("windowspc_mcp.uia.controls.get_window_rect", return_value=(0, 0, 800, 600))
    @patch("windowspc_mcp.uia.controls.get_window_title", return_value="App")
    def test_uia_exception_caught(self, mock_title, mock_rect):
        svc = _make_service()
        svc._client.uia.ElementFromHandle.side_effect = RuntimeError("COM fail")
        interactive, scrollable = [], []
        # Should not raise
        svc._extract_from_window(12345, interactive, scrollable)


# ── _traverse ────────────────────────────────────────────────────────────────

class TestTraverse:
    def test_depth_limit_stops_recursion(self):
        svc = _make_service()
        element = _make_element()
        _setup_walker_no_children(svc)

        interactive, scrollable = [], []
        window_box = BoundingBox(left=0, top=0, right=1920, bottom=1080)
        svc._traverse(element, window_box, "App", interactive, scrollable, depth=26)
        # Should return immediately — no property reads
        element.GetCurrentPropertyValue.assert_not_called()

    def test_offscreen_element_skipped_but_children_traversed(self):
        svc = _make_service()
        parent = _make_element(is_offscreen=True)
        child = _make_element(name="ChildBtn", role_id=9)
        _setup_walker_with_children(svc, parent, [child])
        # Child has no children
        svc._client.walker.GetFirstChildElement.side_effect = lambda el: (
            child if el is parent else None
        )

        interactive, scrollable = [], []
        window_box = BoundingBox(left=0, top=0, right=1920, bottom=1080)
        svc._traverse(parent, window_box, "App", interactive, scrollable, depth=0)
        # Child should have been classified
        assert len(interactive) == 1
        assert interactive[0].name == "ChildBtn"

    def test_disabled_element_not_classified(self):
        svc = _make_service()
        element = _make_element(is_enabled=False)
        _setup_walker_no_children(svc)

        interactive, scrollable = [], []
        window_box = BoundingBox(left=0, top=0, right=1920, bottom=1080)
        svc._traverse(element, window_box, "App", interactive, scrollable, depth=0)
        assert interactive == []

    def test_non_control_element_skipped(self):
        svc = _make_service()
        element = _make_element(is_control=False)
        _setup_walker_no_children(svc)

        interactive, scrollable = [], []
        window_box = BoundingBox(left=0, top=0, right=1920, bottom=1080)
        svc._traverse(element, window_box, "App", interactive, scrollable, depth=0)
        assert interactive == []

    def test_valid_button_classified(self):
        svc = _make_service()
        element = _make_element(
            control_type_id=50000,  # ButtonControl
            name="Save",
            role_id=9,  # PushButton
        )
        _setup_walker_no_children(svc)

        interactive, scrollable = [], []
        window_box = BoundingBox(left=0, top=0, right=1920, bottom=1080)
        svc._traverse(element, window_box, "App", interactive, scrollable, depth=0)
        assert len(interactive) == 1
        assert interactive[0].name == "Save"
        assert interactive[0].control_type == "Button"

    def test_element_clipped_to_window_and_screen(self):
        # Element extends beyond window and screen
        svc = _make_service(BoundingBox(left=0, top=0, right=500, bottom=500))
        element = _make_element(
            rect=_make_rect(left=0, top=0, right=1000, bottom=1000),
            role_id=9,
        )
        _setup_walker_no_children(svc)

        interactive, scrollable = [], []
        window_box = BoundingBox(left=0, top=0, right=800, bottom=600)
        svc._traverse(element, window_box, "App", interactive, scrollable, depth=0)
        assert len(interactive) == 1
        # Clipped to intersection of window (800x600) and screen (500x500)
        bb = interactive[0].bounding_box
        assert bb.right == 500
        assert bb.bottom == 500

    def test_element_outside_screen_not_classified(self):
        svc = _make_service(BoundingBox(left=0, top=0, right=500, bottom=500))
        element = _make_element(
            rect=_make_rect(left=600, top=600, right=800, bottom=800),
            role_id=9,
        )
        _setup_walker_no_children(svc)

        interactive, scrollable = [], []
        window_box = BoundingBox(left=0, top=0, right=1920, bottom=1080)
        svc._traverse(element, window_box, "App", interactive, scrollable, depth=0)
        assert interactive == []

    def test_invalid_bbox_skips_classification(self):
        svc = _make_service()
        element = _make_element(
            rect=_make_rect(left=0, top=0, right=0, bottom=0),
            role_id=9,
        )
        _setup_walker_no_children(svc)

        interactive, scrollable = [], []
        window_box = BoundingBox(left=0, top=0, right=1920, bottom=1080)
        svc._traverse(element, window_box, "App", interactive, scrollable, depth=0)
        assert interactive == []

    def test_property_read_exception_does_not_stop_traversal(self):
        svc = _make_service()
        element = MagicMock()
        element.GetCurrentPropertyValue.side_effect = RuntimeError("COM error")
        element.CurrentBoundingRectangle = _make_rect()
        _setup_walker_no_children(svc)

        interactive, scrollable = [], []
        window_box = BoundingBox(left=0, top=0, right=1920, bottom=1080)
        # Should not raise
        svc._traverse(element, window_box, "App", interactive, scrollable, depth=0)

    def test_walker_exception_handled(self):
        svc = _make_service()
        element = _make_element(control_type_id=50020, role_id=29)  # TextControl (not interactive)
        svc._client.walker.GetFirstChildElement.side_effect = RuntimeError("walker died")

        interactive, scrollable = [], []
        window_box = BoundingBox(left=0, top=0, right=1920, bottom=1080)
        # Should not raise
        svc._traverse(element, window_box, "App", interactive, scrollable, depth=0)


# ── _classify_element ────────────────────────────────────────────────────────

class TestClassifyElement:
    def _classify(self, svc, element, control_type_name="ButtonControl"):
        interactive, scrollable = [], []
        clipped = BoundingBox(left=10, top=10, right=200, bottom=50)
        svc._classify_element(element, control_type_name, clipped, "Win", interactive, scrollable)
        return interactive, scrollable

    def test_interactive_button_added(self):
        svc = _make_service()
        element = _make_element(name="Apply", role_id=9)  # PushButton
        interactive, scrollable = self._classify(svc, element, "ButtonControl")
        assert len(interactive) == 1
        assert interactive[0].name == "Apply"
        assert interactive[0].control_type == "Button"

    def test_non_interactive_control_type_ignored(self):
        svc = _make_service()
        element = _make_element(name="Panel", role_id=0)
        interactive, scrollable = self._classify(svc, element, "PaneControl")
        assert interactive == []

    def test_edit_control_bypasses_role_check(self):
        """EditControl and ComboBoxControl are always interactive regardless of role."""
        svc = _make_service()
        element = _make_element(name="Search", control_type_id=50004, role_id=0)
        interactive, scrollable = self._classify(svc, element, "EditControl")
        assert len(interactive) == 1

    def test_combobox_bypasses_role_check(self):
        svc = _make_service()
        element = _make_element(name="Dropdown", control_type_id=50003, role_id=0)
        interactive, scrollable = self._classify(svc, element, "ComboBoxControl")
        assert len(interactive) == 1

    def test_interactive_type_but_non_interactive_role_filtered(self):
        """ButtonControl with role 'Default' (not in INTERACTIVE_ROLES) is filtered out."""
        svc = _make_service()
        element = _make_element(name="FakeBtn", control_type_id=50000, role_id=0)
        interactive, scrollable = self._classify(svc, element, "ButtonControl")
        assert interactive == []

    def test_document_control_type_interactive(self):
        svc = _make_service()
        element = _make_element(name="Doc", control_type_id=50030, role_id=29)  # Text role
        interactive, scrollable = self._classify(svc, element, "DocumentControl")
        assert len(interactive) == 1

    def test_role_exception_still_adds_element(self):
        """If getting role raises, element is assumed interactive by control type."""
        svc = _make_service()
        element = _make_element(name="Btn")
        # Make role property raise
        original_side_effect = element.GetCurrentPropertyValue.side_effect

        def prop_value_with_role_error(prop_id):
            if prop_id == UIA_LegacyIAccessibleRolePropertyId:
                raise RuntimeError("no role")
            return original_side_effect(prop_id)

        element.GetCurrentPropertyValue.side_effect = prop_value_with_role_error
        interactive, scrollable = self._classify(svc, element, "ButtonControl")
        assert len(interactive) == 1

    def test_scrollable_element_detected(self):
        svc = _make_service()
        element = _make_element(
            name="ListView",
            v_scrollable=True,
            h_scrollable=False,
            v_scroll_pct=33.3,
        )
        interactive, scrollable = self._classify(svc, element, "ListControl")
        assert len(scrollable) == 1
        assert scrollable[0].name == "ListView"
        assert scrollable[0].metadata["vertical_scrollable"] is True
        assert scrollable[0].metadata["horizontal_scrollable"] is False
        assert scrollable[0].metadata["vertical_scroll_percent"] == 33.3

    def test_scrollable_with_no_name_uses_control_type(self):
        svc = _make_service()
        element = _make_element(name="", v_scrollable=True)
        interactive, scrollable = self._classify(svc, element, "PaneControl")
        assert len(scrollable) == 1
        assert scrollable[0].name == "PaneControl"

    def test_both_interactive_and_scrollable(self):
        """An element can be both scrollable and interactive."""
        svc = _make_service()
        element = _make_element(
            name="ComboList",
            control_type_id=50003,  # ComboBox
            role_id=11,  # ComboBox role
            v_scrollable=True,
        )
        interactive, scrollable = self._classify(svc, element, "ComboBoxControl")
        assert len(scrollable) == 1
        assert len(interactive) == 1

    def test_negative_scroll_percent_clamped_to_zero(self):
        svc = _make_service()
        element = _make_element(v_scrollable=True, v_scroll_pct=-1.0)
        interactive, scrollable = self._classify(svc, element, "PaneControl")
        assert scrollable[0].metadata["vertical_scroll_percent"] == 0

    def test_scroll_exception_handled(self):
        svc = _make_service()
        element = MagicMock()
        element.GetCurrentPropertyValue.side_effect = RuntimeError("scroll fail")
        interactive, scrollable = self._classify(svc, element, "PaneControl")
        # No crash, nothing added (PaneControl not in interactive set)
        assert scrollable == []
        assert interactive == []


# ── _get_name ────────────────────────────────────────────────────────────────

class TestGetName:
    def test_returns_stripped_name(self):
        svc = _make_service()
        element = _make_element(name="  Hello  ")
        assert svc._get_name(element) == "Hello"

    def test_returns_empty_on_none(self):
        svc = _make_service()
        element = MagicMock()
        element.GetCurrentPropertyValue.return_value = None
        assert svc._get_name(element) == ""

    def test_returns_empty_on_exception(self):
        svc = _make_service()
        element = MagicMock()
        element.GetCurrentPropertyValue.side_effect = RuntimeError("COM")
        assert svc._get_name(element) == ""


# ── _extract_metadata ───────────────────────────────────────────────────────

class TestExtractMetadata:
    def test_has_focused(self):
        svc = _make_service()
        element = _make_element(has_focus=True)
        meta = svc._extract_metadata(element, "ButtonControl")
        assert meta["has_focused"] is True

    def test_has_focused_false(self):
        svc = _make_service()
        element = _make_element(has_focus=False)
        meta = svc._extract_metadata(element, "ButtonControl")
        assert meta["has_focused"] is False

    def test_focus_exception_defaults_false(self):
        svc = _make_service()
        element = MagicMock()
        element.GetCurrentPropertyValue.side_effect = RuntimeError("no focus")
        meta = svc._extract_metadata(element, "ButtonControl")
        assert meta["has_focused"] is False

    def test_accelerator_key(self):
        svc = _make_service()
        element = _make_element(accel_key="Ctrl+S")
        meta = svc._extract_metadata(element, "ButtonControl")
        assert meta["shortcut"] == "Ctrl+S"

    def test_no_accelerator_key(self):
        svc = _make_service()
        element = _make_element(accel_key="")
        meta = svc._extract_metadata(element, "ButtonControl")
        assert "shortcut" not in meta

    def test_help_text(self):
        svc = _make_service()
        element = _make_element(help_text="Click to save")
        meta = svc._extract_metadata(element, "ButtonControl")
        assert meta["help_text"] == "Click to save"

    def test_help_text_truncated_to_100(self):
        svc = _make_service()
        element = _make_element(help_text="X" * 200)
        meta = svc._extract_metadata(element, "ButtonControl")
        assert len(meta["help_text"]) == 100

    def test_no_help_text(self):
        svc = _make_service()
        element = _make_element(help_text="")
        meta = svc._extract_metadata(element, "ButtonControl")
        assert "help_text" not in meta

    def test_edit_control_value(self):
        svc = _make_service()
        element = _make_element(value="hello world")
        meta = svc._extract_metadata(element, "EditControl")
        assert meta["value"] == "hello world"

    def test_edit_control_value_truncated_to_200(self):
        svc = _make_service()
        element = _make_element(value="V" * 300)
        meta = svc._extract_metadata(element, "EditControl")
        assert len(meta["value"]) == 200

    def test_edit_control_password(self):
        svc = _make_service()
        element = _make_element(value="secret", is_password=True)
        meta = svc._extract_metadata(element, "EditControl")
        assert meta["is_password"] is True

    def test_edit_control_not_password(self):
        svc = _make_service()
        element = _make_element(value="text", is_password=False)
        meta = svc._extract_metadata(element, "EditControl")
        assert "is_password" not in meta

    def test_non_edit_skips_value(self):
        svc = _make_service()
        element = _make_element(value="something")
        meta = svc._extract_metadata(element, "ButtonControl")
        assert "value" not in meta

    def test_button_toggle_on(self):
        svc = _make_service()
        element = _make_element(toggle_state=1)
        meta = svc._extract_metadata(element, "ButtonControl")
        assert meta["toggle_state"] == "on"

    def test_checkbox_toggle_off(self):
        svc = _make_service()
        element = _make_element(toggle_state=0)
        meta = svc._extract_metadata(element, "CheckBoxControl")
        assert meta["toggle_state"] == "off"

    def test_toggle_none_means_no_key(self):
        svc = _make_service()
        element = _make_element(toggle_state=None)
        meta = svc._extract_metadata(element, "ButtonControl")
        assert "toggle_state" not in meta

    def test_non_button_skips_toggle(self):
        svc = _make_service()
        element = _make_element(toggle_state=1)
        meta = svc._extract_metadata(element, "EditControl")
        assert "toggle_state" not in meta

    def test_accel_exception_ignored(self):
        svc = _make_service()
        element = _make_element(has_focus=False)

        original = element.GetCurrentPropertyValue.side_effect

        def prop_with_accel_error(prop_id):
            if prop_id == UIA_AcceleratorKeyPropertyId:
                raise RuntimeError("no accel")
            return original(prop_id)

        element.GetCurrentPropertyValue.side_effect = prop_with_accel_error
        meta = svc._extract_metadata(element, "ButtonControl")
        assert "shortcut" not in meta

    def test_help_text_exception_ignored(self):
        svc = _make_service()
        element = _make_element(has_focus=False)

        original = element.GetCurrentPropertyValue.side_effect

        def prop_with_help_error(prop_id):
            if prop_id == UIA_HelpTextPropertyId:
                raise RuntimeError("no help")
            return original(prop_id)

        element.GetCurrentPropertyValue.side_effect = prop_with_help_error
        meta = svc._extract_metadata(element, "ButtonControl")
        assert "help_text" not in meta


# ── Integration-style: full get_state with mocked windows ────────────────────

class TestGetStateIntegration:
    """Runs get_state end-to-end with mock windows and elements."""

    @patch("windowspc_mcp.uia.controls.get_window_rect", return_value=(0, 0, 800, 600))
    @patch("windowspc_mcp.uia.controls.get_window_title", return_value="Notepad")
    def test_full_extraction(self, mock_title, mock_rect):
        svc = _make_service()
        button = _make_element(name="Save", control_type_id=50000, role_id=9)
        svc._client.uia.ElementFromHandle.return_value = button
        _setup_walker_no_children(svc)

        state = svc.get_state(window_handles=[12345])
        assert len(state.interactive_nodes) == 1
        assert state.interactive_nodes[0].name == "Save"
        assert state.interactive_nodes[0].window_name == "Notepad"

    @patch("windowspc_mcp.uia.controls.get_window_rect", return_value=(0, 0, 800, 600))
    @patch("windowspc_mcp.uia.controls.get_window_title", return_value="App")
    def test_scrollable_extraction(self, mock_title, mock_rect):
        svc = _make_service()
        pane = _make_element(
            name="ContentPane",
            control_type_id=50033,  # PaneControl
            v_scrollable=True,
            v_scroll_pct=50.0,
        )
        svc._client.uia.ElementFromHandle.return_value = pane
        _setup_walker_no_children(svc)

        state = svc.get_state(window_handles=[12345])
        assert len(state.scrollable_nodes) == 1
        assert state.scrollable_nodes[0].metadata["vertical_scroll_percent"] == 50.0
