"""Tests for ipc.frames – FrameBuffer."""

import pytest
from windowspc_mcp.ipc.frames import FrameBuffer


class TestFrameBufferInit:
    """FrameBuffer starts with no frame."""

    def test_initial_frame_is_none(self):
        fb = FrameBuffer()
        assert fb.get_frame() is None


class TestFrameBufferPush:
    """push_frame stores data retrievable by get_frame."""

    def test_push_single_frame(self):
        fb = FrameBuffer()
        data = b"\x00\x01\x02"
        fb.push_frame(data, 100, 200)
        result = fb.get_frame()
        assert result == (data, 100, 200)

    def test_push_overwrites_previous(self):
        fb = FrameBuffer()
        fb.push_frame(b"first", 10, 20)
        fb.push_frame(b"second", 30, 40)
        result = fb.get_frame()
        assert result == (b"second", 30, 40)

    def test_push_empty_bytes(self):
        fb = FrameBuffer()
        fb.push_frame(b"", 0, 0)
        result = fb.get_frame()
        assert result == (b"", 0, 0)

    def test_push_large_frame(self):
        fb = FrameBuffer()
        data = b"\xff" * (1920 * 1080 * 4)
        fb.push_frame(data, 1920, 1080)
        result = fb.get_frame()
        assert result[0] is data
        assert result[1] == 1920
        assert result[2] == 1080


class TestFrameBufferGet:
    """get_frame returns the exact stored tuple."""

    def test_get_returns_tuple_of_three(self):
        fb = FrameBuffer()
        fb.push_frame(b"abc", 5, 10)
        result = fb.get_frame()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_get_frame_bytes_identity(self):
        fb = FrameBuffer()
        data = b"pixel_data"
        fb.push_frame(data, 640, 480)
        assert fb.get_frame()[0] is data

    def test_get_frame_multiple_times_same_result(self):
        fb = FrameBuffer()
        fb.push_frame(b"data", 320, 240)
        assert fb.get_frame() == fb.get_frame()

    def test_get_frame_dimensions(self):
        fb = FrameBuffer()
        fb.push_frame(b"\x00", 1920, 1080)
        _, w, h = fb.get_frame()
        assert w == 1920
        assert h == 1080


class TestFrameBufferMultipleInstances:
    """Separate FrameBuffer instances are independent."""

    def test_independent_buffers(self):
        fb1 = FrameBuffer()
        fb2 = FrameBuffer()
        fb1.push_frame(b"a", 1, 2)
        assert fb2.get_frame() is None

    def test_both_buffers_hold_different_data(self):
        fb1 = FrameBuffer()
        fb2 = FrameBuffer()
        fb1.push_frame(b"one", 10, 20)
        fb2.push_frame(b"two", 30, 40)
        assert fb1.get_frame() == (b"one", 10, 20)
        assert fb2.get_frame() == (b"two", 30, 40)
