"""Production-grade tests for windowspc_mcp.display.manager."""

import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from windowspc_mcp.display.manager import DisplayInfo, DisplayManager


# =========================================================================
# DisplayInfo
# =========================================================================


class TestDisplayInfoBoundaryProperties:
    """left, top, right, bottom property accessors."""

    def test_left_equals_x(self):
        d = DisplayInfo(device_name="D", x=100, y=200, width=800, height=600)
        assert d.left == 100

    def test_top_equals_y(self):
        d = DisplayInfo(device_name="D", x=100, y=200, width=800, height=600)
        assert d.top == 200

    def test_right_equals_x_plus_width(self):
        d = DisplayInfo(device_name="D", x=100, y=200, width=800, height=600)
        assert d.right == 900

    def test_bottom_equals_y_plus_height(self):
        d = DisplayInfo(device_name="D", x=100, y=200, width=800, height=600)
        assert d.bottom == 800

    def test_zero_origin(self):
        d = DisplayInfo(device_name="D", x=0, y=0, width=1920, height=1080)
        assert d.left == 0 and d.top == 0 and d.right == 1920 and d.bottom == 1080

    def test_negative_origin(self):
        d = DisplayInfo(device_name="D", x=-1920, y=-500, width=1920, height=1080)
        assert d.left == -1920
        assert d.top == -500
        assert d.right == 0
        assert d.bottom == 580


class TestDisplayInfoContainsPoint:
    """contains_point: inclusive left/top, exclusive right/bottom."""

    @pytest.fixture()
    def display(self):
        return DisplayInfo(device_name="D", x=100, y=200, width=800, height=600)

    def test_point_inside(self, display):
        assert display.contains_point(500, 500)

    def test_point_outside_left(self, display):
        assert not display.contains_point(99, 400)

    def test_point_outside_above(self, display):
        assert not display.contains_point(500, 199)

    def test_point_outside_right(self, display):
        assert not display.contains_point(900, 400)

    def test_point_outside_below(self, display):
        assert not display.contains_point(500, 800)

    def test_boundary_top_left_inclusive(self, display):
        assert display.contains_point(100, 200)

    def test_boundary_right_exclusive(self, display):
        assert not display.contains_point(900, 200)

    def test_boundary_bottom_exclusive(self, display):
        assert not display.contains_point(100, 800)

    def test_boundary_just_inside_right(self, display):
        assert display.contains_point(899, 799)

    def test_boundary_just_inside_bottom(self, display):
        assert display.contains_point(100, 799)

    def test_negative_coordinates(self):
        d = DisplayInfo(device_name="D", x=-100, y=-100, width=200, height=200)
        assert d.contains_point(-1, -1)
        assert d.contains_point(-100, -100)
        assert not d.contains_point(100, 100)


class TestDisplayInfoToRelative:
    """to_relative: absolute -> display-local."""

    def test_basic_conversion(self):
        d = DisplayInfo(device_name="D", x=3840, y=0, width=1920, height=1080)
        assert d.to_relative(4340, 300) == (500, 300)

    def test_origin(self):
        d = DisplayInfo(device_name="D", x=3840, y=100, width=1920, height=1080)
        assert d.to_relative(3840, 100) == (0, 0)

    def test_negative_result(self):
        d = DisplayInfo(device_name="D", x=100, y=100, width=800, height=600)
        assert d.to_relative(0, 0) == (-100, -100)


class TestDisplayInfoToAbsolute:
    """to_absolute: display-local -> absolute."""

    def test_basic_conversion(self):
        d = DisplayInfo(device_name="D", x=3840, y=0, width=1920, height=1080)
        assert d.to_absolute(500, 300) == (4340, 300)

    def test_origin(self):
        d = DisplayInfo(device_name="D", x=3840, y=100, width=1920, height=1080)
        assert d.to_absolute(0, 0) == (3840, 100)

    def test_roundtrip(self):
        d = DisplayInfo(device_name="D", x=3840, y=100, width=1920, height=1080)
        abs_coords = d.to_absolute(500, 300)
        assert d.to_relative(*abs_coords) == (500, 300)


# =========================================================================
# DisplayManager properties
# =========================================================================


class TestDisplayManagerProperties:
    """agent_display and is_ready properties."""

    def test_agent_display_none_initially(self):
        dm = DisplayManager()
        assert dm.agent_display is None

    def test_is_ready_false_initially(self):
        dm = DisplayManager()
        assert dm.is_ready is False

    def test_is_ready_true_when_set(self):
        dm = DisplayManager()
        dm._agent_display = DisplayInfo("V", 0, 0, 1920, 1080, is_agent=True)
        assert dm.is_ready is True

    def test_agent_display_returns_stored_value(self):
        dm = DisplayManager()
        d = DisplayInfo("V", 100, 200, 1920, 1080, is_agent=True)
        dm._agent_display = d
        assert dm.agent_display is d


# =========================================================================
# check_driver
# =========================================================================


class TestCheckDriver:
    """check_driver: success and failure paths."""

    def test_success(self):
        mock_vdd = MagicMock()
        mock_module = MagicMock()
        mock_module.ParsecVDD.return_value = mock_vdd
        with patch.dict("sys.modules", {"windowspc_mcp.display.driver": mock_module}):
            dm = DisplayManager()
            assert dm.check_driver() is True
            mock_module.ParsecVDD.assert_called_once()
            mock_vdd.close.assert_called_once()

    def test_failure_returns_false(self):
        mock_module = MagicMock()
        mock_module.ParsecVDD.side_effect = OSError("no driver")
        with patch.dict("sys.modules", {"windowspc_mcp.display.driver": mock_module}):
            dm = DisplayManager()
            assert dm.check_driver() is False


# =========================================================================
# create_display
# =========================================================================


class TestCreateDisplay:
    """create_display: fresh path, crash recovery, already-exists error, display not appearing."""

    def _mock_driver_and_identity(self):
        """Return (mock_driver_module, mock_identity_module) with sensible defaults."""
        driver = MagicMock()
        vdd_inst = MagicMock()
        vdd_inst.add_display.return_value = 0
        driver.ParsecVDD.return_value = vdd_inst

        identity = MagicMock()
        identity.load_state.return_value = None
        identity.PersistedDisplayState = MagicMock()

        return driver, identity

    def test_raises_when_agent_already_exists(self):
        dm = DisplayManager()
        dm._agent_display = DisplayInfo("V", 0, 0, 1920, 1080, is_agent=True)
        with pytest.raises(RuntimeError, match="already exists"):
            dm.create_display()

    @patch("time.sleep")
    def test_fresh_creation_success(self, mock_sleep):
        dm = DisplayManager()
        driver, identity = self._mock_driver_and_identity()

        existing = DisplayInfo(r"\\.\DISPLAY1", 0, 0, 1920, 1080)
        new_mon = DisplayInfo(r"\\.\DISPLAY2", 1920, 0, 1920, 1080)

        # enumerate_monitors returns existing before, then existing+new after
        with patch.dict("sys.modules", {
            "windowspc_mcp.display.driver": driver,
            "windowspc_mcp.display.identity": identity,
        }):
            # First call: before set; second call: find_new_display; third: find_by_name
            with patch.object(dm, "enumerate_monitors", return_value=[existing, new_mon]):
                with patch.object(dm, "_find_new_display", return_value=new_mon):
                    with patch.object(dm, "_set_resolution"):
                        with patch.object(dm, "_find_display_by_name", return_value=new_mon):
                            result = dm.create_display(1920, 1080)

                            assert result.device_name == r"\\.\DISPLAY2"
                            assert result.is_agent is True
                            assert dm.agent_display is result
                            identity.save_state.assert_called_once()

    @patch("time.sleep")
    def test_crash_recovery_reconnects_existing_display(self, mock_sleep):
        dm = DisplayManager()
        driver, identity = self._mock_driver_and_identity()

        saved_state = MagicMock()
        saved_state.device_name = r"\\.\DISPLAY3"
        saved_state.display_index = 2
        identity.load_state.return_value = saved_state

        existing_display = DisplayInfo(r"\\.\DISPLAY3", 3840, 0, 1920, 1080)

        with patch.dict("sys.modules", {
            "windowspc_mcp.display.driver": driver,
            "windowspc_mcp.display.identity": identity,
        }):
            with patch.object(dm, "_find_display_by_name", return_value=existing_display):
                result = dm.create_display()

                assert result.device_name == r"\\.\DISPLAY3"
                assert result.is_agent is True
                assert dm._display_index == 2
                # Should NOT call save_state again since we reconnected
                identity.save_state.assert_not_called()

    @patch("time.sleep")
    def test_crash_recovery_stale_state_clears_and_creates_fresh(self, mock_sleep):
        dm = DisplayManager()
        driver, identity = self._mock_driver_and_identity()

        saved_state = MagicMock()
        saved_state.device_name = r"\\.\DISPLAY_GONE"
        identity.load_state.return_value = saved_state

        new_mon = DisplayInfo(r"\\.\DISPLAY2", 1920, 0, 1920, 1080)

        with patch.dict("sys.modules", {
            "windowspc_mcp.display.driver": driver,
            "windowspc_mcp.display.identity": identity,
        }):
            # _find_display_by_name returns None for stale name, then the new display
            with patch.object(dm, "_find_display_by_name", side_effect=[None, new_mon]):
                with patch.object(dm, "enumerate_monitors", return_value=[]):
                    with patch.object(dm, "_find_new_display", return_value=new_mon):
                        with patch.object(dm, "_set_resolution"):
                            result = dm.create_display()

                            identity.clear_state.assert_called_once()
                            assert result.is_agent is True

    @patch("time.sleep")
    def test_display_not_appearing_raises(self, mock_sleep):
        dm = DisplayManager()
        driver, identity = self._mock_driver_and_identity()

        with patch.dict("sys.modules", {
            "windowspc_mcp.display.driver": driver,
            "windowspc_mcp.display.identity": identity,
        }):
            with patch.object(dm, "enumerate_monitors", return_value=[]):
                with patch.object(dm, "_find_new_display", return_value=None):
                    with pytest.raises(RuntimeError, match="did not appear"):
                        dm.create_display()

    @patch("time.sleep")
    def test_crash_recovery_vdd_reopen_fails_gracefully(self, mock_sleep):
        """If re-opening VDD for keepalive fails during reconnect, we still succeed."""
        dm = DisplayManager()
        driver, identity = self._mock_driver_and_identity()
        driver.ParsecVDD.side_effect = OSError("handle unavailable")

        saved_state = MagicMock()
        saved_state.device_name = r"\\.\DISPLAY3"
        saved_state.display_index = 1
        identity.load_state.return_value = saved_state

        existing = DisplayInfo(r"\\.\DISPLAY3", 3840, 0, 1920, 1080)

        with patch.dict("sys.modules", {
            "windowspc_mcp.display.driver": driver,
            "windowspc_mcp.display.identity": identity,
        }):
            with patch.object(dm, "_find_display_by_name", return_value=existing):
                result = dm.create_display()
                assert result.is_agent is True
                assert dm._vdd is None  # VDD reopen failed

    @patch("time.sleep")
    def test_final_find_by_name_returns_none_uses_original(self, mock_sleep):
        """When _find_display_by_name returns None after resolution set, use original display."""
        dm = DisplayManager()
        driver, identity = self._mock_driver_and_identity()

        new_mon = DisplayInfo(r"\\.\DISPLAY2", 1920, 0, 1920, 1080)

        with patch.dict("sys.modules", {
            "windowspc_mcp.display.driver": driver,
            "windowspc_mcp.display.identity": identity,
        }):
            with patch.object(dm, "enumerate_monitors", return_value=[]):
                with patch.object(dm, "_find_new_display", return_value=new_mon):
                    with patch.object(dm, "_set_resolution"):
                        with patch.object(dm, "_find_display_by_name", return_value=None):
                            result = dm.create_display()
                            assert result is new_mon
                            assert result.is_agent is True


# =========================================================================
# destroy_display
# =========================================================================


class TestDestroyDisplay:
    """destroy_display: full cleanup and error paths."""

    def test_full_cleanup(self):
        dm = DisplayManager()
        dm._agent_display = DisplayInfo("V", 0, 0, 1920, 1080, is_agent=True)
        mock_vdd = MagicMock()
        dm._vdd = mock_vdd
        dm._display_index = 0

        mock_identity = MagicMock()
        with patch.dict("sys.modules", {"windowspc_mcp.display.identity": mock_identity}):
            with patch.object(dm, "_migrate_windows_to_primary") as mock_migrate:
                dm.destroy_display()

                mock_migrate.assert_called_once()
                mock_vdd.remove_display.assert_called_once_with(0)
                mock_vdd.close.assert_called_once()
                mock_identity.clear_state.assert_called_once()
                assert dm._agent_display is None
                assert dm._vdd is None
                assert dm._display_index is None

    def test_remove_display_error_does_not_stop_cleanup(self):
        dm = DisplayManager()
        dm._agent_display = DisplayInfo("V", 0, 0, 1920, 1080, is_agent=True)
        mock_vdd = MagicMock()
        mock_vdd.remove_display.side_effect = RuntimeError("boom")
        dm._vdd = mock_vdd
        dm._display_index = 0

        mock_identity = MagicMock()
        with patch.dict("sys.modules", {"windowspc_mcp.display.identity": mock_identity}):
            with patch.object(dm, "_migrate_windows_to_primary"):
                dm.destroy_display()
                mock_vdd.close.assert_called_once()
                mock_identity.clear_state.assert_called_once()
                assert dm._vdd is None

    def test_close_error_does_not_stop_cleanup(self):
        dm = DisplayManager()
        mock_vdd = MagicMock()
        mock_vdd.close.side_effect = RuntimeError("close boom")
        dm._vdd = mock_vdd
        dm._display_index = 0

        mock_identity = MagicMock()
        with patch.dict("sys.modules", {"windowspc_mcp.display.identity": mock_identity}):
            dm.destroy_display()
            mock_identity.clear_state.assert_called_once()
            assert dm._vdd is None

    def test_no_agent_no_vdd(self):
        dm = DisplayManager()
        mock_identity = MagicMock()
        with patch.dict("sys.modules", {"windowspc_mcp.display.identity": mock_identity}):
            dm.destroy_display()
            mock_identity.clear_state.assert_called_once()

    def test_agent_but_no_vdd(self):
        dm = DisplayManager()
        dm._agent_display = DisplayInfo("V", 0, 0, 1920, 1080, is_agent=True)
        mock_identity = MagicMock()
        with patch.dict("sys.modules", {"windowspc_mcp.display.identity": mock_identity}):
            with patch.object(dm, "_migrate_windows_to_primary") as mock_migrate:
                dm.destroy_display()
                mock_migrate.assert_called_once()
                assert dm._agent_display is None

    def test_vdd_but_no_display_index(self):
        """When _display_index is None, skip remove_display but still close VDD."""
        dm = DisplayManager()
        mock_vdd = MagicMock()
        dm._vdd = mock_vdd
        dm._display_index = None

        mock_identity = MagicMock()
        with patch.dict("sys.modules", {"windowspc_mcp.display.identity": mock_identity}):
            dm.destroy_display()
            mock_vdd.remove_display.assert_not_called()
            mock_vdd.close.assert_called_once()


# =========================================================================
# enumerate_monitors
# =========================================================================


class TestEnumerateMonitors:
    """enumerate_monitors: with/without win32api, exception handling."""

    def test_returns_empty_when_win32api_unavailable(self):
        dm = DisplayManager()
        with patch.dict("sys.modules", {"win32api": None, "win32con": None}):
            assert dm.enumerate_monitors() == []

    def test_returns_empty_when_enum_raises(self):
        mock_api = MagicMock()
        mock_con = MagicMock()
        mock_api.EnumDisplayMonitors.side_effect = OSError("display error")
        with patch.dict("sys.modules", {"win32api": mock_api, "win32con": mock_con}):
            dm = DisplayManager()
            assert dm.enumerate_monitors() == []

    def test_returns_display_info_list(self):
        mock_api = MagicMock()
        mock_con = MagicMock()
        mock_api.EnumDisplayMonitors.return_value = [
            (1, None, (0, 0, 1920, 1080)),
            (2, None, (1920, 0, 3840, 1080)),
        ]
        with patch.dict("sys.modules", {"win32api": mock_api, "win32con": mock_con}):
            dm = DisplayManager()
            with patch.object(dm, "_device_name_for_rect", side_effect=[r"\\.\DISPLAY1", r"\\.\DISPLAY2"]):
                monitors = dm.enumerate_monitors()
                assert len(monitors) == 2
                assert monitors[0].device_name == r"\\.\DISPLAY1"
                assert monitors[0].x == 0
                assert monitors[0].width == 1920
                assert monitors[1].device_name == r"\\.\DISPLAY2"
                assert monitors[1].x == 1920

    def test_device_name_none_becomes_empty_string(self):
        mock_api = MagicMock()
        mock_con = MagicMock()
        mock_api.EnumDisplayMonitors.return_value = [(1, None, (0, 0, 1920, 1080))]
        with patch.dict("sys.modules", {"win32api": mock_api, "win32con": mock_con}):
            dm = DisplayManager()
            with patch.object(dm, "_device_name_for_rect", return_value=None):
                monitors = dm.enumerate_monitors()
                assert monitors[0].device_name == ""


# =========================================================================
# refresh_bounds
# =========================================================================


class TestRefreshBounds:
    """refresh_bounds: with and without agent display."""

    def test_noop_when_no_agent(self):
        dm = DisplayManager()
        dm.refresh_bounds()  # no error
        assert dm._agent_display is None

    def test_updates_agent_display(self):
        dm = DisplayManager()
        original = DisplayInfo(r"\\.\D3", 0, 0, 1920, 1080, is_agent=True)
        dm._agent_display = original

        updated = DisplayInfo(r"\\.\D3", 100, 200, 1920, 1080)
        with patch.object(dm, "_find_display_by_name", return_value=updated):
            dm.refresh_bounds()
            assert dm._agent_display.x == 100
            assert dm._agent_display.y == 200
            assert dm._agent_display.is_agent is True

    def test_display_not_found_keeps_original(self):
        dm = DisplayManager()
        original = DisplayInfo(r"\\.\D3", 0, 0, 1920, 1080, is_agent=True)
        dm._agent_display = original

        with patch.object(dm, "_find_display_by_name", return_value=None):
            dm.refresh_bounds()
            assert dm._agent_display is original


# =========================================================================
# _find_new_display
# =========================================================================


class TestFindNewDisplay:
    """_find_new_display: ParsecVDA found, fallback, no new, import error."""

    def test_parsec_vda_found(self):
        dm = DisplayManager()
        existing = DisplayInfo(r"\\.\D1", 0, 0, 1920, 1080)
        new_mon = DisplayInfo(r"\\.\D2", 1920, 0, 1920, 1080)

        mock_api = MagicMock()
        mock_con = MagicMock()
        dev_info = MagicMock()
        dev_info.DeviceString = "ParsecVDA Display Adapter"
        mock_api.EnumDisplayDevices.return_value = dev_info

        with patch.dict("sys.modules", {"win32api": mock_api, "win32con": mock_con}):
            with patch.object(dm, "enumerate_monitors", return_value=[existing, new_mon]):
                result = dm._find_new_display({r"\\.\D1"})
                assert result is new_mon

    def test_fallback_when_not_parsec(self):
        """Non-ParsecVDA device string: first loop skips it, fallback returns any new."""
        dm = DisplayManager()
        existing = DisplayInfo(r"\\.\D1", 0, 0, 1920, 1080)
        new_mon = DisplayInfo(r"\\.\D2", 1920, 0, 1920, 1080)

        mock_api = MagicMock()
        mock_con = MagicMock()
        dev_info = MagicMock()
        dev_info.DeviceString = "Generic PnP Monitor"
        mock_api.EnumDisplayDevices.return_value = dev_info

        with patch.dict("sys.modules", {"win32api": mock_api, "win32con": mock_con}):
            with patch.object(dm, "enumerate_monitors", return_value=[existing, new_mon]):
                result = dm._find_new_display({r"\\.\D1"})
                assert result is new_mon

    def test_enum_display_devices_raises_returns_new_anyway(self):
        dm = DisplayManager()
        existing = DisplayInfo(r"\\.\D1", 0, 0, 1920, 1080)
        new_mon = DisplayInfo(r"\\.\D2", 1920, 0, 1920, 1080)

        mock_api = MagicMock()
        mock_con = MagicMock()
        mock_api.EnumDisplayDevices.side_effect = OSError("query failed")

        with patch.dict("sys.modules", {"win32api": mock_api, "win32con": mock_con}):
            with patch.object(dm, "enumerate_monitors", return_value=[existing, new_mon]):
                result = dm._find_new_display({r"\\.\D1"})
                assert result is new_mon

    def test_no_new_monitors(self):
        dm = DisplayManager()
        existing = DisplayInfo(r"\\.\D1", 0, 0, 1920, 1080)

        mock_api = MagicMock()
        mock_con = MagicMock()

        with patch.dict("sys.modules", {"win32api": mock_api, "win32con": mock_con}):
            with patch.object(dm, "enumerate_monitors", return_value=[existing]):
                result = dm._find_new_display({r"\\.\D1"})
                assert result is None

    def test_import_error_returns_none(self):
        dm = DisplayManager()
        with patch.dict("sys.modules", {"win32api": None, "win32con": None}):
            assert dm._find_new_display(set()) is None


# =========================================================================
# _set_resolution
# =========================================================================


class TestSetResolution:
    """_set_resolution: success, warning, exception."""

    def _setup_win32_mocks(self):
        mock_api = MagicMock()
        mock_con = MagicMock()
        mock_pywintypes = MagicMock()
        mock_con.DM_PELSWIDTH = 0x80000
        mock_con.DM_PELSHEIGHT = 0x100000
        mock_con.CDS_UPDATEREGISTRY = 0x01
        mock_dm = MagicMock()
        mock_api.EnumDisplaySettings.return_value = mock_dm
        return mock_api, mock_con, mock_pywintypes, mock_dm

    def test_success(self):
        mock_api, mock_con, mock_pywintypes, mock_dm = self._setup_win32_mocks()
        mock_api.ChangeDisplaySettingsEx.return_value = 0

        with patch.dict("sys.modules", {
            "win32api": mock_api, "win32con": mock_con, "pywintypes": mock_pywintypes,
        }):
            dm = DisplayManager()
            dm._set_resolution(r"\\.\D2", 1920, 1080)
            mock_api.ChangeDisplaySettingsEx.assert_called_once()
            assert mock_dm.PelsWidth == 1920
            assert mock_dm.PelsHeight == 1080

    def test_nonzero_result_logs_warning(self):
        mock_api, mock_con, mock_pywintypes, mock_dm = self._setup_win32_mocks()
        mock_api.ChangeDisplaySettingsEx.return_value = 1

        with patch.dict("sys.modules", {
            "win32api": mock_api, "win32con": mock_con, "pywintypes": mock_pywintypes,
        }):
            dm = DisplayManager()
            dm._set_resolution(r"\\.\D2", 1920, 1080)  # no exception

    def test_exception_caught(self):
        mock_api = MagicMock()
        mock_con = MagicMock()
        mock_pywintypes = MagicMock()
        mock_api.EnumDisplaySettings.side_effect = OSError("fail")

        with patch.dict("sys.modules", {
            "win32api": mock_api, "win32con": mock_con, "pywintypes": mock_pywintypes,
        }):
            dm = DisplayManager()
            dm._set_resolution(r"\\.\D2", 1920, 1080)  # should not raise


# =========================================================================
# _migrate_windows_to_primary
# =========================================================================


class TestMigrateWindowsToPrimary:
    """_migrate_windows_to_primary: window movement and error handling."""

    def test_noop_when_no_agent_display(self):
        dm = DisplayManager()
        dm._migrate_windows_to_primary()  # no error

    def test_migrates_window_on_agent_display(self):
        dm = DisplayManager()
        dm._agent_display = DisplayInfo("V", 1920, 0, 1920, 1080, is_agent=True)

        primary = DisplayInfo("P", 0, 0, 1920, 1080)
        mock_controls = MagicMock()
        mock_controls.enumerate_windows.return_value = [100]
        mock_controls.is_window_visible.return_value = True
        mock_controls.get_window_rect.return_value = (2000, 100, 800, 600)

        with patch.dict("sys.modules", {"windowspc_mcp.uia.controls": mock_controls}):
            with patch.object(dm, "_get_primary_display", return_value=primary):
                dm._migrate_windows_to_primary()
                mock_controls.move_window.assert_called_once_with(100, 0, 0, 800, 600)

    def test_skips_invisible_windows(self):
        dm = DisplayManager()
        dm._agent_display = DisplayInfo("V", 1920, 0, 1920, 1080, is_agent=True)

        mock_controls = MagicMock()
        mock_controls.enumerate_windows.return_value = [100]
        mock_controls.is_window_visible.return_value = False

        with patch.dict("sys.modules", {"windowspc_mcp.uia.controls": mock_controls}):
            with patch.object(dm, "_get_primary_display", return_value=None):
                dm._migrate_windows_to_primary()
                mock_controls.move_window.assert_not_called()

    def test_skips_window_with_none_rect(self):
        dm = DisplayManager()
        dm._agent_display = DisplayInfo("V", 1920, 0, 1920, 1080, is_agent=True)

        mock_controls = MagicMock()
        mock_controls.enumerate_windows.return_value = [100]
        mock_controls.is_window_visible.return_value = True
        mock_controls.get_window_rect.return_value = None

        with patch.dict("sys.modules", {"windowspc_mcp.uia.controls": mock_controls}):
            with patch.object(dm, "_get_primary_display", return_value=None):
                dm._migrate_windows_to_primary()
                mock_controls.move_window.assert_not_called()

    def test_skips_window_not_on_agent_display(self):
        dm = DisplayManager()
        dm._agent_display = DisplayInfo("V", 1920, 0, 1920, 1080, is_agent=True)

        mock_controls = MagicMock()
        mock_controls.enumerate_windows.return_value = [100]
        mock_controls.is_window_visible.return_value = True
        # Window center at (500, 400) is on primary, not agent
        mock_controls.get_window_rect.return_value = (100, 100, 800, 600)

        with patch.dict("sys.modules", {"windowspc_mcp.uia.controls": mock_controls}):
            with patch.object(dm, "_get_primary_display", return_value=None):
                dm._migrate_windows_to_primary()
                mock_controls.move_window.assert_not_called()

    def test_exception_caught_gracefully(self):
        dm = DisplayManager()
        dm._agent_display = DisplayInfo("V", 1920, 0, 1920, 1080, is_agent=True)

        with patch.dict("sys.modules", {"windowspc_mcp.uia.controls": None}):
            # ImportError is caught
            dm._migrate_windows_to_primary()

    def test_uses_origin_when_no_primary(self):
        """When _get_primary_display returns None, target is (0, 0)."""
        dm = DisplayManager()
        dm._agent_display = DisplayInfo("V", 1920, 0, 1920, 1080, is_agent=True)

        mock_controls = MagicMock()
        mock_controls.enumerate_windows.return_value = [100]
        mock_controls.is_window_visible.return_value = True
        mock_controls.get_window_rect.return_value = (2000, 100, 800, 600)

        with patch.dict("sys.modules", {"windowspc_mcp.uia.controls": mock_controls}):
            with patch.object(dm, "_get_primary_display", return_value=None):
                dm._migrate_windows_to_primary()
                mock_controls.move_window.assert_called_once_with(100, 0, 0, 800, 600)


# =========================================================================
# _get_primary_display
# =========================================================================


class TestGetPrimaryDisplay:
    """_get_primary_display: origin found and fallback."""

    def test_origin_found(self):
        dm = DisplayManager()
        primary = DisplayInfo(r"\\.\D1", 0, 0, 1920, 1080)
        secondary = DisplayInfo(r"\\.\D2", 1920, 0, 1920, 1080)
        with patch.object(dm, "enumerate_monitors", return_value=[secondary, primary]):
            result = dm._get_primary_display()
            assert result is primary

    def test_fallback_to_first_monitor(self):
        dm = DisplayManager()
        off_origin = DisplayInfo(r"\\.\D1", 100, 100, 1920, 1080)
        with patch.object(dm, "enumerate_monitors", return_value=[off_origin]):
            result = dm._get_primary_display()
            assert result is off_origin

    def test_empty_list_returns_none(self):
        dm = DisplayManager()
        with patch.object(dm, "enumerate_monitors", return_value=[]):
            result = dm._get_primary_display()
            assert result is None


# =========================================================================
# _device_name_for_rect
# =========================================================================


class TestDeviceNameForRect:
    """_device_name_for_rect: match, no match, exception."""

    def test_match_found(self):
        dm = DisplayManager()
        mock_api = MagicMock()

        dev = MagicMock()
        dev.DeviceName = r"\\.\DISPLAY1"
        mock_api.EnumDisplayDevices.return_value = dev

        settings = MagicMock()
        settings.Position_x = 0
        settings.Position_y = 0
        settings.PelsWidth = 1920
        settings.PelsHeight = 1080
        mock_api.EnumDisplaySettings.return_value = settings

        with patch.dict("sys.modules", {"win32api": mock_api}):
            result = dm._device_name_for_rect(0, 0, 1920, 1080)
            assert result == r"\\.\DISPLAY1"

    def test_no_match(self):
        dm = DisplayManager()
        mock_api = MagicMock()

        dev = MagicMock()
        dev.DeviceName = r"\\.\DISPLAY1"
        mock_api.EnumDisplayDevices.return_value = dev

        settings = MagicMock()
        settings.Position_x = 0
        settings.Position_y = 0
        settings.PelsWidth = 1920
        settings.PelsHeight = 1080
        mock_api.EnumDisplaySettings.return_value = settings

        # Second call raises to break the loop
        mock_api.EnumDisplayDevices.side_effect = [dev, Exception("end")]

        with patch.dict("sys.modules", {"win32api": mock_api}):
            result = dm._device_name_for_rect(3840, 0, 5760, 1080)
            assert result is None

    def test_empty_device_name_stops_iteration(self):
        dm = DisplayManager()
        mock_api = MagicMock()

        dev = MagicMock()
        dev.DeviceName = ""
        mock_api.EnumDisplayDevices.return_value = dev

        with patch.dict("sys.modules", {"win32api": mock_api}):
            result = dm._device_name_for_rect(0, 0, 1920, 1080)
            assert result is None

    def test_outer_exception_returns_none(self):
        dm = DisplayManager()
        with patch.dict("sys.modules", {"win32api": None}):
            # Import fails -> outer except catches it
            result = dm._device_name_for_rect(0, 0, 1920, 1080)
            assert result is None

    def test_enum_display_settings_exception_continues(self):
        """When EnumDisplaySettings raises for one device, continue to next."""
        dm = DisplayManager()
        mock_api = MagicMock()

        dev1 = MagicMock()
        dev1.DeviceName = r"\\.\DISPLAY1"
        dev2 = MagicMock()
        dev2.DeviceName = r"\\.\DISPLAY2"
        dev3 = MagicMock()
        dev3.DeviceName = ""

        mock_api.EnumDisplayDevices.side_effect = [dev1, dev2, dev3]
        mock_api.EnumDisplaySettings.side_effect = [
            OSError("fail"),  # dev1 fails
        ]

        with patch.dict("sys.modules", {"win32api": mock_api}):
            result = dm._device_name_for_rect(0, 0, 1920, 1080)
            # dev1 settings fail, dev2 never gets called because we need side_effect
            assert result is None
