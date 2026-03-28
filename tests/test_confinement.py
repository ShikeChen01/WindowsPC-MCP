import pytest
from windowsmcp_custom.confinement.engine import ConfinementEngine, ConfinementError, ActionType
from tests.conftest import MockBounds


@pytest.fixture
def engine():
    e = ConfinementEngine()
    e.set_agent_bounds(MockBounds(x=3840, y=0, width=1920, height=1080))
    return e


class TestActionClassification:
    def test_classify_read_tools(self, engine):
        assert engine.classify_action("Screenshot") == ActionType.READ
        assert engine.classify_action("Snapshot") == ActionType.READ

    def test_classify_write_tools(self, engine):
        assert engine.classify_action("Click") == ActionType.WRITE
        assert engine.classify_action("Type") == ActionType.WRITE
        assert engine.classify_action("Move") == ActionType.WRITE
        assert engine.classify_action("Scroll") == ActionType.WRITE
        assert engine.classify_action("Shortcut") == ActionType.WRITE
        assert engine.classify_action("App") == ActionType.WRITE
        assert engine.classify_action("MultiSelect") == ActionType.WRITE
        assert engine.classify_action("MultiEdit") == ActionType.WRITE

    def test_classify_unconfined_tools(self, engine):
        assert engine.classify_action("PowerShell") == ActionType.UNCONFINED
        assert engine.classify_action("FileSystem") == ActionType.UNCONFINED
        assert engine.classify_action("Clipboard") == ActionType.UNCONFINED


class TestCoordinateValidation:
    def test_valid_relative_coords(self, engine):
        ax, ay = engine.validate_and_translate(500, 300)
        assert ax == 4340
        assert ay == 300

    def test_origin(self, engine):
        ax, ay = engine.validate_and_translate(0, 0)
        assert ax == 3840
        assert ay == 0

    def test_max_bounds(self, engine):
        ax, ay = engine.validate_and_translate(1919, 1079)
        assert ax == 5759
        assert ay == 1079

    def test_out_of_bounds_x(self, engine):
        with pytest.raises(ConfinementError, match="out of bounds"):
            engine.validate_and_translate(1920, 500)

    def test_out_of_bounds_negative(self, engine):
        with pytest.raises(ConfinementError, match="out of bounds"):
            engine.validate_and_translate(-1, 500)

    def test_no_agent_display(self):
        engine = ConfinementEngine()
        with pytest.raises(ConfinementError, match="no agent display"):
            engine.validate_and_translate(100, 100)


class TestPointOnAgentScreen:
    def test_absolute_point_on_agent(self, engine):
        assert engine.is_point_on_agent_screen(4000, 500)

    def test_absolute_point_on_user(self, engine):
        assert not engine.is_point_on_agent_screen(100, 500)


class TestShortcutFiltering:
    def test_allowed_shortcut(self):
        from windowsmcp_custom.confinement.shortcuts import is_shortcut_allowed
        assert is_shortcut_allowed("ctrl+c")
        assert is_shortcut_allowed("Ctrl+S")
        assert is_shortcut_allowed("F5")

    def test_blocked_shortcut(self):
        from windowsmcp_custom.confinement.shortcuts import is_shortcut_allowed
        assert not is_shortcut_allowed("alt+tab")
        assert not is_shortcut_allowed("win+d")
        assert not is_shortcut_allowed("ctrl+alt+del")

    def test_win_modifier_blocked_by_default(self):
        from windowsmcp_custom.confinement.shortcuts import is_shortcut_allowed
        assert not is_shortcut_allowed("win+x")
        assert not is_shortcut_allowed("win+shift+s")
