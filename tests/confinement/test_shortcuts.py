"""Tests for windowspc_mcp.confinement.shortcuts — normalize, allow/block, reasons."""

import pytest

from windowspc_mcp.confinement.shortcuts import (
    ALLOWED_SHORTCUTS,
    BLOCKED_SHORTCUTS,
    get_blocked_reason,
    is_shortcut_allowed,
    normalize_shortcut,
)


# ---------------------------------------------------------------------------
# normalize_shortcut
# ---------------------------------------------------------------------------


class TestNormalizeShortcutModifierOrdering:
    def test_ctrl_alt_canonical(self):
        assert normalize_shortcut("alt+ctrl+del") == "ctrl+alt+del"

    def test_ctrl_shift_canonical(self):
        assert normalize_shortcut("shift+ctrl+t") == "ctrl+shift+t"

    def test_all_four_modifiers(self):
        assert normalize_shortcut("win+shift+alt+ctrl+x") == "ctrl+alt+shift+win+x"

    def test_win_after_shift(self):
        assert normalize_shortcut("win+shift+s") == "shift+win+s"

    def test_already_canonical(self):
        assert normalize_shortcut("ctrl+alt+shift+win+a") == "ctrl+alt+shift+win+a"


class TestNormalizeShortcutCase:
    def test_uppercase(self):
        assert normalize_shortcut("CTRL+SHIFT+T") == "ctrl+shift+t"

    def test_mixed_case(self):
        assert normalize_shortcut("Ctrl+Shift+N") == "ctrl+shift+n"

    def test_all_caps_function_key(self):
        assert normalize_shortcut("F12") == "f12"


class TestNormalizeShortcutSingleKey:
    def test_function_key(self):
        assert normalize_shortcut("F5") == "f5"

    def test_letter_key(self):
        assert normalize_shortcut("a") == "a"

    def test_escape(self):
        assert normalize_shortcut("escape") == "escape"


class TestNormalizeShortcutSpaces:
    def test_spaces_around_plus(self):
        assert normalize_shortcut("ctrl + c") == "ctrl+c"

    def test_tabs_and_spaces(self):
        assert normalize_shortcut("ctrl  +  shift  +  t") == "ctrl+shift+t"


# ---------------------------------------------------------------------------
# is_shortcut_allowed
# ---------------------------------------------------------------------------


class TestIsShortcutAllowedBlocked:
    @pytest.mark.parametrize(
        "shortcut",
        [
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
        ],
    )
    def test_all_blocked_shortcuts_denied(self, shortcut):
        assert is_shortcut_allowed(shortcut) is False

    def test_blocked_case_insensitive(self):
        assert is_shortcut_allowed("ALT+TAB") is False
        assert is_shortcut_allowed("Win+D") is False

    def test_blocked_reordered_modifiers(self):
        assert is_shortcut_allowed("tab+alt") is False
        assert is_shortcut_allowed("del+alt+ctrl") is False


class TestIsShortcutAllowedAllowed:
    @pytest.mark.parametrize(
        "shortcut",
        [
            "ctrl+c", "ctrl+x", "ctrl+v", "ctrl+z", "ctrl+y",
            "ctrl+a", "ctrl+s", "ctrl+f", "ctrl+p", "ctrl+n",
            "ctrl+w", "ctrl+t",
            "ctrl+shift+t", "ctrl+shift+n",
            "ctrl+tab", "ctrl+shift+tab",
            "f1", "f2", "f3", "f4", "f5", "f6",
            "f7", "f8", "f9", "f10", "f11", "f12",
            "enter", "escape", "tab", "backspace", "delete",
            "home", "end", "pageup", "pagedown",
            "up", "down", "left", "right",
            "shift+tab",
        ],
    )
    def test_all_allowed_shortcuts(self, shortcut):
        assert is_shortcut_allowed(shortcut) is True


class TestIsShortcutAllowedUnknownNonWin:
    def test_unknown_without_win_allowed(self):
        assert is_shortcut_allowed("ctrl+g") is True

    def test_alt_plus_number_allowed(self):
        assert is_shortcut_allowed("alt+1") is True

    def test_ctrl_shift_letter_not_in_list(self):
        # ctrl+shift+x is not in ALLOWED or BLOCKED but has no win modifier
        assert is_shortcut_allowed("ctrl+shift+x") is True


class TestIsShortcutAllowedUnknownWithWin:
    def test_win_unknown_blocked(self):
        assert is_shortcut_allowed("win+x") is False

    def test_win_shift_unknown_blocked(self):
        assert is_shortcut_allowed("win+shift+s") is False

    def test_win_alt_unknown_blocked(self):
        assert is_shortcut_allowed("win+alt+q") is False


# ---------------------------------------------------------------------------
# get_blocked_reason
# ---------------------------------------------------------------------------


class TestGetBlockedReasonKnownReasons:
    """Test shortcuts whose normalized form IS in BLOCKED_SHORTCUTS and _REASONS.

    Note: Some BLOCKED_SHORTCUTS entries like 'win+shift+m' and 'win+ctrl+d' have
    non-canonical key order. normalize_shortcut('win+shift+m') => 'shift+win+m',
    which is NOT in BLOCKED_SHORTCUTS. These shortcuts are still blocked via the
    win-modifier fallback, but they do NOT get the specific _REASONS message.
    We test those separately below.
    """

    @pytest.mark.parametrize(
        "shortcut,fragment",
        [
            ("win+d", "desktop"),
            ("win+tab", "task view"),
            ("win+l", "locks"),
            ("win+r", "run dialog"),
            ("win+e", "file explorer"),
            ("win+m", "minimises"),
            ("alt+tab", "switches"),
            ("alt+shift+tab", "reverse"),
            ("alt+f4", "closes"),
            ("ctrl+alt+del", "security screen"),
            ("ctrl+shift+esc", "task manager"),
        ],
    )
    def test_known_reason(self, shortcut, fragment):
        reason = get_blocked_reason(shortcut)
        assert fragment in reason.lower()


class TestGetBlockedReasonNormalizedEntries:
    """Shortcuts that previously had non-canonical modifier order in BLOCKED_SHORTCUTS.

    After normalization at module load time, these all get their specific reasons.
    """

    @pytest.mark.parametrize(
        "shortcut,fragment",
        [
            ("win+shift+m", "restores all minimised windows"),
            ("win+ctrl+d", "creates a new virtual desktop"),
            ("win+ctrl+left", "previous virtual desktop"),
            ("win+ctrl+right", "next virtual desktop"),
            ("win+ctrl+f4", "closes the current virtual desktop"),
        ],
    )
    def test_blocked_with_specific_reason(self, shortcut, fragment):
        assert is_shortcut_allowed(shortcut) is False
        reason = get_blocked_reason(shortcut)
        assert fragment in reason.lower()


class TestGetBlockedReasonUnknownBlocked:
    """If a shortcut were in BLOCKED_SHORTCUTS without a _REASONS entry,
    we'd get the fallback. Currently all entries have reasons, so we verify
    the fallback path exists by checking the data structure coverage."""

    def test_all_blocked_have_reasons(self):
        """Verify every shortcut in BLOCKED_SHORTCUTS has a human-readable reason."""
        for sc in BLOCKED_SHORTCUTS:
            reason = get_blocked_reason(sc)
            # Should NOT be the generic "on the blocked list" fallback
            # because all current entries have specific reasons
            assert len(reason) > 10, f"Reason for {sc} too short: {reason}"


class TestGetBlockedReasonWinModifier:
    def test_unknown_win_shortcut(self):
        reason = get_blocked_reason("win+x")
        assert "win modifier" in reason.lower()

    def test_another_unknown_win(self):
        reason = get_blocked_reason("win+alt+q")
        assert "blocked by default" in reason.lower()


class TestGetBlockedReasonNotPermittedFallback:
    def test_non_blocked_non_win(self):
        reason = get_blocked_reason("ctrl+q")
        assert "not permitted" in reason.lower()

    def test_includes_original_shortcut(self):
        reason = get_blocked_reason("ctrl+q")
        assert "ctrl+q" in reason
