"""Tests for AgentInputService — all branches of the input layer."""

import pytest
from unittest.mock import patch, MagicMock, call
from tests.conftest import MockBounds
from windowspc_mcp.confinement.errors import BlockedShortcutError
from windowspc_mcp.input.service import (
    AgentInputService,
    _make_vk_input,
    _parse_vk,
    _escape_text,
    VK_MAP,
    VK_CTRL,
    VK_SHIFT,
    VK_ALT,
    VK_RETURN,
    VK_HOME,
    VK_END,
    VK_BACK,
    VK_A,
    INPUT_KEYBOARD,
    KEYEVENTF_KEYUP,
)


# ---------------------------------------------------------------------------
# Module paths for patching
# ---------------------------------------------------------------------------
_SVC = "windowspc_mcp.input.service"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def bounds():
    return MockBounds(x=3840, y=0, width=1920, height=1080)


@pytest.fixture
def svc(bounds):
    """AgentInputService wired to a mock bounds provider."""
    return AgentInputService(agent_bounds_fn=lambda: bounds)


@pytest.fixture
def svc_no_bounds():
    """AgentInputService whose bounds provider returns None."""
    return AgentInputService(agent_bounds_fn=lambda: None)


# ===================================================================
# Helper functions
# ===================================================================


class TestMakeVkInput:
    def test_keyboard_type(self):
        inp = _make_vk_input(VK_CTRL, 0)
        assert inp.type == INPUT_KEYBOARD

    def test_key_down_flags(self):
        inp = _make_vk_input(VK_A, 0)
        assert inp._input.ki.wVk == VK_A
        assert inp._input.ki.dwFlags == 0

    def test_key_up_flags(self):
        inp = _make_vk_input(VK_A, KEYEVENTF_KEYUP)
        assert inp._input.ki.dwFlags == KEYEVENTF_KEYUP


class TestParseVk:
    def test_known_named_keys(self):
        assert _parse_vk("ctrl") == VK_CTRL
        assert _parse_vk("shift") == VK_SHIFT
        assert _parse_vk("alt") == VK_ALT
        assert _parse_vk("enter") == VK_RETURN
        assert _parse_vk("home") == VK_HOME
        assert _parse_vk("end") == VK_END
        assert _parse_vk("backspace") == VK_BACK

    def test_case_insensitive(self):
        assert _parse_vk("Ctrl") == VK_CTRL
        assert _parse_vk("SHIFT") == VK_SHIFT
        assert _parse_vk("  Alt  ") == VK_ALT

    def test_function_keys(self):
        assert _parse_vk("f1") == 0x70
        assert _parse_vk("f12") == 0x7B

    def test_single_character(self):
        assert _parse_vk("a") == ord("A")
        assert _parse_vk("z") == ord("Z")
        assert _parse_vk("5") == ord("5")

    def test_unknown_key_raises(self):
        with pytest.raises(ValueError, match="Unknown key"):
            _parse_vk("nonexistent")

    def test_empty_strip_multichar_unknown(self):
        with pytest.raises(ValueError, match="Unknown key"):
            _parse_vk("xx")


class TestEscapeText:
    def test_no_special_chars(self):
        assert _escape_text("hello") == "hello"

    def test_braces_escaped(self):
        assert _escape_text("{test}") == "{{}test{}}"

    def test_parens_escaped(self):
        assert _escape_text("(x)") == "{(}x{)}"

    def test_caret_percent_tilde(self):
        assert _escape_text("^+%~") == "{^}{+}{%}{~}"

    def test_brackets_escaped(self):
        assert _escape_text("[a]") == "{[}a{]}"

    def test_mixed(self):
        assert _escape_text("a+b") == "a{+}b"


# ===================================================================
# Initialization
# ===================================================================


class TestInit:
    def test_stores_bounds_fn(self, bounds):
        fn = lambda: bounds
        svc = AgentInputService(agent_bounds_fn=fn)
        assert svc._get_bounds is fn


# ===================================================================
# Focus management
# ===================================================================


class TestFindForegroundOnAgentScreen:
    @patch(f"{_SVC}.get_window_rect", return_value=(4000, 100, 4400, 400))
    @patch(f"{_SVC}.get_foreground_window", return_value=12345)
    def test_foreground_on_agent(self, mock_fg, mock_rect, svc):
        result = svc._find_foreground_on_agent_screen()
        assert result == 12345

    @patch(f"{_SVC}.get_window_rect", return_value=(100, 100, 500, 400))
    @patch(f"{_SVC}.get_foreground_window", return_value=12345)
    def test_foreground_not_on_agent(self, mock_fg, mock_rect, svc):
        """Window center is on the user screen, not the agent screen."""
        result = svc._find_foreground_on_agent_screen()
        assert result is None

    @patch(f"{_SVC}.get_foreground_window", return_value=0)
    def test_no_foreground_window(self, mock_fg, svc):
        result = svc._find_foreground_on_agent_screen()
        assert result is None

    @patch(f"{_SVC}.get_window_rect", return_value=None)
    @patch(f"{_SVC}.get_foreground_window", return_value=99)
    def test_rect_returns_none(self, mock_fg, mock_rect, svc):
        result = svc._find_foreground_on_agent_screen()
        assert result is None

    def test_bounds_none(self, svc_no_bounds):
        result = svc_no_bounds._find_foreground_on_agent_screen()
        assert result is None


class TestFindWindowAt:
    @patch(f"{_SVC}.get_window_rect", return_value=(4000, 0, 4500, 500))
    @patch(f"{_SVC}.is_window_visible", return_value=True)
    @patch(f"{_SVC}.enumerate_windows", return_value=[111])
    def test_finds_window(self, mock_enum, mock_vis, mock_rect, svc):
        result = svc._find_window_at(4200, 250)
        assert result == 111

    @patch(f"{_SVC}.is_window_visible", return_value=False)
    @patch(f"{_SVC}.enumerate_windows", return_value=[222])
    def test_skips_invisible(self, mock_enum, mock_vis, svc):
        result = svc._find_window_at(100, 100)
        assert result is None

    @patch(f"{_SVC}.get_window_rect", return_value=(0, 0, 50, 50))
    @patch(f"{_SVC}.is_window_visible", return_value=True)
    @patch(f"{_SVC}.enumerate_windows", return_value=[333])
    def test_point_outside_window(self, mock_enum, mock_vis, mock_rect, svc):
        result = svc._find_window_at(999, 999)
        assert result is None

    @patch(f"{_SVC}.enumerate_windows", return_value=[])
    def test_no_windows(self, mock_enum, svc):
        result = svc._find_window_at(100, 100)
        assert result is None

    @patch(f"{_SVC}.get_window_rect", return_value=None)
    @patch(f"{_SVC}.is_window_visible", return_value=True)
    @patch(f"{_SVC}.enumerate_windows", return_value=[444])
    def test_rect_none_skips(self, mock_enum, mock_vis, mock_rect, svc):
        result = svc._find_window_at(100, 100)
        assert result is None


class TestEnsureFocus:
    @patch(f"{_SVC}.time.sleep")
    @patch(f"{_SVC}.set_foreground_window")
    @patch(f"{_SVC}.get_foreground_window", return_value=1)
    @patch(f"{_SVC}.get_window_rect", return_value=(4000, 0, 4500, 500))
    @patch(f"{_SVC}.is_window_visible", return_value=True)
    @patch(f"{_SVC}.enumerate_windows", return_value=[2])
    def test_switches_focus(self, mock_enum, mock_vis, mock_rect,
                            mock_fg, mock_setfg, mock_sleep, svc):
        svc._ensure_focus(4200, 250)
        mock_setfg.assert_called_once_with(2)
        mock_sleep.assert_called_once_with(0.05)

    @patch(f"{_SVC}.set_foreground_window")
    @patch(f"{_SVC}.get_foreground_window", return_value=5)
    @patch(f"{_SVC}.get_window_rect", return_value=(0, 0, 500, 500))
    @patch(f"{_SVC}.is_window_visible", return_value=True)
    @patch(f"{_SVC}.enumerate_windows", return_value=[5])
    def test_already_focused(self, mock_enum, mock_vis, mock_rect,
                             mock_fg, mock_setfg, svc):
        svc._ensure_focus(250, 250)
        mock_setfg.assert_not_called()

    @patch(f"{_SVC}.set_foreground_window")
    @patch(f"{_SVC}.enumerate_windows", return_value=[])
    def test_no_window_at_coords(self, mock_enum, mock_setfg, svc):
        svc._ensure_focus(9999, 9999)
        mock_setfg.assert_not_called()


# ===================================================================
# Clicking
# ===================================================================


class TestClick:
    @patch(f"{_SVC}.click_at")
    @patch.object(AgentInputService, "_ensure_focus")
    def test_left_click(self, mock_focus, mock_click, svc):
        result = svc.click(4200, 300, button="left", clicks=1)
        mock_focus.assert_called_once_with(4200, 300)
        mock_click.assert_called_once_with(4200, 300, "left", 1)
        assert "4200" in result
        assert "300" in result
        assert "left" in result
        assert "x1" in result

    @patch(f"{_SVC}.click_at")
    @patch.object(AgentInputService, "_ensure_focus")
    def test_right_click(self, mock_focus, mock_click, svc):
        result = svc.click(4500, 100, button="right", clicks=1)
        mock_click.assert_called_once_with(4500, 100, "right", 1)
        assert "right" in result

    @patch(f"{_SVC}.click_at")
    @patch.object(AgentInputService, "_ensure_focus")
    def test_double_click(self, mock_focus, mock_click, svc):
        result = svc.click(4200, 300, button="left", clicks=2)
        mock_click.assert_called_once_with(4200, 300, "left", 2)
        assert "x2" in result

    @patch(f"{_SVC}.click_at")
    @patch.object(AgentInputService, "_ensure_focus")
    def test_defaults(self, mock_focus, mock_click, svc):
        result = svc.click(4200, 300)
        mock_click.assert_called_once_with(4200, 300, "left", 1)


# ===================================================================
# Typing
# ===================================================================


class TestTypeText:
    @patch(f"{_SVC}.raw_type_text")
    @patch(f"{_SVC}.time.sleep")
    def test_simple_type(self, mock_sleep, mock_raw, svc):
        result = svc.type_text("hello")
        mock_raw.assert_called_once_with("hello")
        assert "5 chars" in result

    @patch(f"{_SVC}.raw_type_text")
    @patch(f"{_SVC}.click_at")
    @patch.object(AgentInputService, "_ensure_focus")
    @patch(f"{_SVC}.time.sleep")
    def test_type_with_position(self, mock_sleep, mock_focus, mock_click,
                                mock_raw, svc):
        result = svc.type_text("hi", abs_x=4200, abs_y=300)
        mock_focus.assert_called_once_with(4200, 300)
        mock_click.assert_called_once_with(4200, 300, "left", 1)
        assert "at (4200, 300)" in result

    @patch(f"{_SVC}.send_input")
    @patch(f"{_SVC}.raw_type_text")
    @patch(f"{_SVC}.time.sleep")
    def test_type_with_clear(self, mock_sleep, mock_raw, mock_send, svc):
        result = svc.type_text("new text", clear=True)
        # clear triggers: Ctrl+A -> Backspace via send_input
        assert mock_send.call_count == 2  # Ctrl+A, Backspace
        assert "cleared first" in result

    @patch(f"{_SVC}.send_input")
    @patch(f"{_SVC}.raw_type_text")
    @patch(f"{_SVC}.time.sleep")
    def test_type_with_caret_start(self, mock_sleep, mock_raw, mock_send, svc):
        result = svc.type_text("x", caret_position="start")
        # Home key down + up
        assert mock_send.call_count == 1
        assert "caret=start" in result

    @patch(f"{_SVC}.send_input")
    @patch(f"{_SVC}.raw_type_text")
    @patch(f"{_SVC}.time.sleep")
    def test_type_with_caret_end(self, mock_sleep, mock_raw, mock_send, svc):
        result = svc.type_text("x", caret_position="end")
        assert mock_send.call_count == 1
        assert "caret=end" in result

    @patch(f"{_SVC}.send_input")
    @patch(f"{_SVC}.raw_type_text")
    @patch(f"{_SVC}.time.sleep")
    def test_type_with_press_enter(self, mock_sleep, mock_raw, mock_send, svc):
        result = svc.type_text("query", press_enter=True)
        # Enter key down + up
        assert mock_send.call_count == 1
        assert "pressed Enter" in result

    @patch(f"{_SVC}.send_input")
    @patch(f"{_SVC}.raw_type_text")
    @patch(f"{_SVC}.time.sleep")
    def test_type_idle_caret_no_extra_keys(self, mock_sleep, mock_raw,
                                           mock_send, svc):
        result = svc.type_text("x", caret_position="idle")
        mock_send.assert_not_called()
        assert "caret=" not in result

    @patch(f"{_SVC}.send_input")
    @patch(f"{_SVC}.raw_type_text")
    @patch(f"{_SVC}.click_at")
    @patch.object(AgentInputService, "_ensure_focus")
    @patch(f"{_SVC}.time.sleep")
    def test_type_all_options(self, mock_sleep, mock_focus, mock_click,
                              mock_raw, mock_send, svc):
        result = svc.type_text(
            "full",
            abs_x=4200, abs_y=300,
            clear=True,
            caret_position="end",
            press_enter=True,
        )
        mock_focus.assert_called_once()
        mock_click.assert_called_once()
        mock_raw.assert_called_once_with("full")
        assert "at (4200, 300)" in result
        assert "cleared first" in result
        assert "caret=end" in result
        assert "pressed Enter" in result

    @patch(f"{_SVC}.raw_type_text")
    @patch(f"{_SVC}.time.sleep")
    def test_type_no_options_no_detail(self, mock_sleep, mock_raw, svc):
        result = svc.type_text("abc")
        assert result == "Typed 3 chars"

    @patch(f"{_SVC}.click_at")
    @patch.object(AgentInputService, "_ensure_focus")
    @patch(f"{_SVC}.raw_type_text")
    @patch(f"{_SVC}.time.sleep")
    def test_abs_x_only_no_focus_click(self, mock_sleep, mock_raw,
                                       mock_focus, mock_click, svc):
        """Only abs_x without abs_y should NOT trigger focus/click,
        but abs_x alone still appears in the result detail string."""
        result = svc.type_text("t", abs_x=100)
        mock_focus.assert_not_called()
        mock_click.assert_not_called()
        # The result string includes "at (100, None)" because only abs_x
        # is checked for the detail suffix
        assert "at (100, None)" in result


# ===================================================================
# Scrolling
# ===================================================================


class TestScroll:
    @patch(f"{_SVC}.scroll_at")
    def test_scroll_down(self, mock_scroll, svc):
        result = svc.scroll(4200, 300, amount=-3)
        mock_scroll.assert_called_once_with(4200, 300, -3, False)
        assert "vertically" in result
        assert "-3" in result

    @patch(f"{_SVC}.scroll_at")
    def test_scroll_up(self, mock_scroll, svc):
        result = svc.scroll(4200, 300, amount=3)
        mock_scroll.assert_called_once_with(4200, 300, 3, False)
        assert "vertically" in result

    @patch(f"{_SVC}.scroll_at")
    def test_scroll_horizontal(self, mock_scroll, svc):
        result = svc.scroll(4200, 300, amount=2, horizontal=True)
        mock_scroll.assert_called_once_with(4200, 300, 2, True)
        assert "horizontally" in result

    @patch(f"{_SVC}.scroll_at")
    def test_scroll_defaults(self, mock_scroll, svc):
        result = svc.scroll(4200, 300)
        mock_scroll.assert_called_once_with(4200, 300, -3, False)


# ===================================================================
# Move / Drag
# ===================================================================


class TestMove:
    @patch(f"{_SVC}.move_cursor")
    @patch(f"{_SVC}.send_input")
    def test_simple_move(self, mock_send, mock_move, svc):
        result = svc.move(4200, 300)
        mock_move.assert_called_once_with(4200, 300)
        mock_send.assert_not_called()
        assert "Moved" in result

    @patch(f"{_SVC}.move_cursor")
    @patch(f"{_SVC}.send_input")
    def test_drag(self, mock_send, mock_move, svc):
        result = svc.move(4200, 300, drag=True)
        mock_move.assert_called_once_with(4200, 300)
        # Two send_input calls: mouse down before move_cursor, mouse up after
        assert mock_send.call_count == 2
        assert "Dragged" in result

    @patch(f"{_SVC}.move_cursor")
    @patch(f"{_SVC}.send_input")
    def test_drag_message(self, mock_send, mock_move, svc):
        result = svc.move(100, 200, drag=True)
        assert result == "Dragged to (100, 200)"

    @patch(f"{_SVC}.move_cursor")
    @patch(f"{_SVC}.send_input")
    def test_move_message(self, mock_send, mock_move, svc):
        result = svc.move(100, 200, drag=False)
        assert result == "Moved to (100, 200)"


# ===================================================================
# Shortcuts
# ===================================================================


class TestSendShortcut:
    @patch(f"{_SVC}.send_input")
    @patch(f"{_SVC}.is_shortcut_allowed", return_value=True)
    def test_simple_allowed(self, mock_allowed, mock_send, svc):
        result = svc.send_shortcut("ctrl+c")
        mock_allowed.assert_called_once_with("ctrl+c")
        mock_send.assert_called_once()
        assert "ctrl+c" in result

    @patch(f"{_SVC}.get_blocked_reason", return_value="test reason")
    @patch(f"{_SVC}.is_shortcut_allowed", return_value=False)
    def test_blocked_raises(self, mock_allowed, mock_reason, svc):
        with pytest.raises(BlockedShortcutError, match="test reason"):
            svc.send_shortcut("alt+tab")

    @patch(f"{_SVC}.send_input")
    @patch(f"{_SVC}.is_shortcut_allowed", return_value=True)
    def test_multi_modifier_shortcut(self, mock_allowed, mock_send, svc):
        result = svc.send_shortcut("ctrl+shift+t")
        mock_send.assert_called_once()
        # 3 keys down + 3 keys up = 6 INPUT structs
        args = mock_send.call_args[0]
        assert len(args) == 6

    @patch(f"{_SVC}.send_input")
    @patch(f"{_SVC}.is_shortcut_allowed", return_value=True)
    def test_single_key_shortcut(self, mock_allowed, mock_send, svc):
        result = svc.send_shortcut("f5")
        mock_send.assert_called_once()
        args = mock_send.call_args[0]
        assert len(args) == 2  # key down + key up

    @patch(f"{_SVC}.send_input")
    @patch(f"{_SVC}.is_shortcut_allowed", return_value=True)
    def test_key_order_reversed_on_release(self, mock_allowed, mock_send, svc):
        """Keys should be released in reverse order."""
        svc.send_shortcut("ctrl+a")
        args = mock_send.call_args[0]
        # args: ctrl_down, a_down, a_up, ctrl_up
        assert len(args) == 4
        # First input: ctrl down
        assert args[0]._input.ki.wVk == VK_CTRL
        assert args[0]._input.ki.dwFlags == 0
        # Second: a down
        assert args[1]._input.ki.wVk == ord("A")
        assert args[1]._input.ki.dwFlags == 0
        # Third: a up (reversed)
        assert args[2]._input.ki.wVk == ord("A")
        assert args[2]._input.ki.dwFlags == KEYEVENTF_KEYUP
        # Fourth: ctrl up
        assert args[3]._input.ki.wVk == VK_CTRL
        assert args[3]._input.ki.dwFlags == KEYEVENTF_KEYUP

    @patch(f"{_SVC}.send_input")
    @patch(f"{_SVC}.is_shortcut_allowed", return_value=True)
    def test_whitespace_in_key_parts(self, mock_allowed, mock_send, svc):
        """Parts are stripped, so spaces around + should work."""
        result = svc.send_shortcut("ctrl + c")
        assert "ctrl + c" in result

    @patch(f"{_SVC}.is_shortcut_allowed", return_value=True)
    def test_invalid_key_raises_valueerror(self, mock_allowed, svc):
        with pytest.raises(ValueError, match="Unknown key"):
            svc.send_shortcut("ctrl+nonexistent")

    @patch(f"{_SVC}.send_input")
    @patch(f"{_SVC}.is_shortcut_allowed", return_value=True)
    def test_empty_parts_filtered(self, mock_allowed, mock_send, svc):
        """Trailing + should not produce empty parts."""
        result = svc.send_shortcut("ctrl+c+")
        # The empty string after trailing + is filtered by `if p.strip()`
        args = mock_send.call_args[0]
        assert len(args) == 4  # ctrl down, c down, c up, ctrl up


# ===================================================================
# Edge cases and integration
# ===================================================================


class TestEdgeCases:
    @patch(f"{_SVC}.raw_type_text")
    @patch(f"{_SVC}.time.sleep")
    def test_empty_text(self, mock_sleep, mock_raw, svc):
        result = svc.type_text("")
        mock_raw.assert_called_once_with("")
        assert "0 chars" in result

    @patch(f"{_SVC}.click_at")
    @patch.object(AgentInputService, "_ensure_focus")
    def test_click_middle_button(self, mock_focus, mock_click, svc):
        result = svc.click(4200, 300, button="middle", clicks=1)
        mock_click.assert_called_once_with(4200, 300, "middle", 1)

    @patch(f"{_SVC}.scroll_at")
    def test_scroll_zero_amount(self, mock_scroll, svc):
        result = svc.scroll(4200, 300, amount=0)
        mock_scroll.assert_called_once_with(4200, 300, 0, False)
        assert "0" in result

    def test_vk_map_completeness(self):
        """All expected keys should be in VK_MAP."""
        expected = {
            "ctrl", "alt", "shift", "enter", "escape", "tab",
            "backspace", "delete", "home", "end", "pageup", "pagedown",
            "up", "down", "left", "right", "space",
            "f1", "f2", "f3", "f4", "f5", "f6",
            "f7", "f8", "f9", "f10", "f11", "f12",
        }
        assert expected == set(VK_MAP.keys())
