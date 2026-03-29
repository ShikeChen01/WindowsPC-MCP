import pytest
from unittest.mock import patch, MagicMock
from windowspc_mcp.display.manager import DisplayManager, DisplayInfo


class TestDisplayInfo:
    def test_contains_point_inside(self):
        info = DisplayInfo(device_name=r"\\.\DISPLAY3", x=3840, y=0, width=1920, height=1080)
        assert info.contains_point(4000, 500)

    def test_contains_point_outside(self):
        info = DisplayInfo(device_name=r"\\.\DISPLAY3", x=3840, y=0, width=1920, height=1080)
        assert not info.contains_point(100, 500)

    def test_contains_point_boundary(self):
        info = DisplayInfo(device_name=r"\\.\DISPLAY3", x=3840, y=0, width=1920, height=1080)
        assert info.contains_point(3840, 0)
        assert not info.contains_point(5760, 0)

    def test_to_relative(self):
        info = DisplayInfo(device_name=r"\\.\DISPLAY3", x=3840, y=0, width=1920, height=1080)
        rx, ry = info.to_relative(4340, 300)
        assert rx == 500 and ry == 300

    def test_to_absolute(self):
        info = DisplayInfo(device_name=r"\\.\DISPLAY3", x=3840, y=0, width=1920, height=1080)
        ax, ay = info.to_absolute(500, 300)
        assert ax == 4340 and ay == 300
