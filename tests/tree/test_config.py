"""Tests for windowspc_mcp.tree.config — control type classifications and constants."""

import pytest

from windowspc_mcp.tree.config import (
    INTERACTIVE_CONTROL_TYPE_NAMES,
    DOCUMENT_CONTROL_TYPE_NAMES,
    INFORMATIVE_CONTROL_TYPE_NAMES,
    INTERACTIVE_ROLES,
    DEFAULT_ACTIONS,
)


class TestInteractiveControlTypeNames:
    """INTERACTIVE_CONTROL_TYPE_NAMES contains exactly the expected interactive controls."""

    def test_is_frozenset(self):
        assert isinstance(INTERACTIVE_CONTROL_TYPE_NAMES, frozenset)

    def test_contains_button(self):
        assert "ButtonControl" in INTERACTIVE_CONTROL_TYPE_NAMES

    def test_contains_edit(self):
        assert "EditControl" in INTERACTIVE_CONTROL_TYPE_NAMES

    def test_contains_checkbox(self):
        assert "CheckBoxControl" in INTERACTIVE_CONTROL_TYPE_NAMES

    def test_contains_radio_button(self):
        assert "RadioButtonControl" in INTERACTIVE_CONTROL_TYPE_NAMES

    def test_contains_combobox(self):
        assert "ComboBoxControl" in INTERACTIVE_CONTROL_TYPE_NAMES

    def test_contains_hyperlink(self):
        assert "HyperlinkControl" in INTERACTIVE_CONTROL_TYPE_NAMES

    def test_contains_list_item(self):
        assert "ListItemControl" in INTERACTIVE_CONTROL_TYPE_NAMES

    def test_contains_menu_item(self):
        assert "MenuItemControl" in INTERACTIVE_CONTROL_TYPE_NAMES

    def test_contains_split_button(self):
        assert "SplitButtonControl" in INTERACTIVE_CONTROL_TYPE_NAMES

    def test_contains_tab_item(self):
        assert "TabItemControl" in INTERACTIVE_CONTROL_TYPE_NAMES

    def test_contains_tree_item(self):
        assert "TreeItemControl" in INTERACTIVE_CONTROL_TYPE_NAMES

    def test_contains_data_item(self):
        assert "DataItemControl" in INTERACTIVE_CONTROL_TYPE_NAMES

    def test_contains_header_item(self):
        assert "HeaderItemControl" in INTERACTIVE_CONTROL_TYPE_NAMES

    def test_contains_spinner(self):
        assert "SpinnerControl" in INTERACTIVE_CONTROL_TYPE_NAMES

    def test_contains_scrollbar(self):
        assert "ScrollBarControl" in INTERACTIVE_CONTROL_TYPE_NAMES

    def test_contains_textbox(self):
        assert "TextBoxControl" in INTERACTIVE_CONTROL_TYPE_NAMES

    def test_does_not_contain_window(self):
        assert "WindowControl" not in INTERACTIVE_CONTROL_TYPE_NAMES

    def test_does_not_contain_pane(self):
        assert "PaneControl" not in INTERACTIVE_CONTROL_TYPE_NAMES

    def test_does_not_contain_document(self):
        """DocumentControl is in its own set, not INTERACTIVE."""
        assert "DocumentControl" not in INTERACTIVE_CONTROL_TYPE_NAMES

    def test_does_not_contain_text(self):
        """TextControl is informative, not interactive."""
        assert "TextControl" not in INTERACTIVE_CONTROL_TYPE_NAMES

    def test_immutable(self):
        with pytest.raises(AttributeError):
            INTERACTIVE_CONTROL_TYPE_NAMES.add("Foo")  # type: ignore[attr-defined]


class TestDocumentControlTypeNames:
    def test_is_frozenset(self):
        assert isinstance(DOCUMENT_CONTROL_TYPE_NAMES, frozenset)

    def test_contains_document(self):
        assert "DocumentControl" in DOCUMENT_CONTROL_TYPE_NAMES

    def test_size(self):
        assert len(DOCUMENT_CONTROL_TYPE_NAMES) == 1


class TestInformativeControlTypeNames:
    def test_is_frozenset(self):
        assert isinstance(INFORMATIVE_CONTROL_TYPE_NAMES, frozenset)

    def test_contains_text(self):
        assert "TextControl" in INFORMATIVE_CONTROL_TYPE_NAMES

    def test_contains_image(self):
        assert "ImageControl" in INFORMATIVE_CONTROL_TYPE_NAMES

    def test_contains_statusbar(self):
        assert "StatusBarControl" in INFORMATIVE_CONTROL_TYPE_NAMES

    def test_disjoint_from_interactive(self):
        """Informative and interactive sets must not overlap."""
        assert INFORMATIVE_CONTROL_TYPE_NAMES.isdisjoint(INTERACTIVE_CONTROL_TYPE_NAMES)

    def test_disjoint_from_document(self):
        assert INFORMATIVE_CONTROL_TYPE_NAMES.isdisjoint(DOCUMENT_CONTROL_TYPE_NAMES)


class TestInteractiveRoles:
    def test_is_frozenset(self):
        assert isinstance(INTERACTIVE_ROLES, frozenset)

    def test_contains_push_button(self):
        assert "PushButton" in INTERACTIVE_ROLES

    def test_contains_link(self):
        assert "Link" in INTERACTIVE_ROLES

    def test_contains_combo_box(self):
        assert "ComboBox" in INTERACTIVE_ROLES

    def test_contains_check_button(self):
        assert "CheckButton" in INTERACTIVE_ROLES

    def test_contains_radio_button(self):
        assert "RadioButton" in INTERACTIVE_ROLES

    def test_contains_menu_item(self):
        assert "MenuItem" in INTERACTIVE_ROLES

    def test_contains_slider(self):
        assert "Slider" in INTERACTIVE_ROLES

    def test_contains_cell(self):
        assert "Cell" in INTERACTIVE_ROLES

    def test_does_not_contain_default(self):
        assert "Default" not in INTERACTIVE_ROLES

    def test_does_not_contain_editabletext(self):
        assert "EditableText" not in INTERACTIVE_ROLES


class TestDefaultActions:
    def test_is_frozenset(self):
        assert isinstance(DEFAULT_ACTIONS, frozenset)

    def test_contains_click(self):
        assert "Click" in DEFAULT_ACTIONS

    def test_contains_press(self):
        assert "Press" in DEFAULT_ACTIONS

    def test_contains_check_uncheck(self):
        assert "Check" in DEFAULT_ACTIONS
        assert "Uncheck" in DEFAULT_ACTIONS

    def test_contains_double_click(self):
        assert "Double Click" in DEFAULT_ACTIONS

    def test_contains_jump(self):
        assert "Jump" in DEFAULT_ACTIONS
