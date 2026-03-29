"""Production-grade tests for windowspc_mcp.display.capture.

All external backends (dxcam, mss, Pillow/ImageGrab) are mocked at the boundary.
"""

import base64
import io
import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from PIL import Image


# =========================================================================
# _capture_dxcam
# =========================================================================


class TestCaptureDxcam:
    """Tests for _capture_dxcam: camera caching, None frame, success."""

    def test_creates_camera_on_first_call(self):
        import windowspc_mcp.display.capture as mod
        old_camera = mod._dxcam_camera
        try:
            mod._dxcam_camera = None
            mock_dxcam = MagicMock()
            mock_camera = MagicMock()
            import numpy as np
            frame = np.zeros((100, 200, 3), dtype=np.uint8)
            mock_camera.grab.return_value = frame
            mock_dxcam.create.return_value = mock_camera

            with patch.object(mod, "dxcam", mock_dxcam):
                result = mod._capture_dxcam(0, 0, 200, 100)
                mock_dxcam.create.assert_called_once()
                assert isinstance(result, Image.Image)
        finally:
            mod._dxcam_camera = old_camera

    def test_reuses_cached_camera(self):
        import windowspc_mcp.display.capture as mod
        old_camera = mod._dxcam_camera
        try:
            mock_camera = MagicMock()
            import numpy as np
            frame = np.zeros((100, 200, 3), dtype=np.uint8)
            mock_camera.grab.return_value = frame
            mod._dxcam_camera = mock_camera

            mock_dxcam = MagicMock()
            with patch.object(mod, "dxcam", mock_dxcam):
                mod._capture_dxcam(0, 0, 200, 100)
                mock_dxcam.create.assert_not_called()
        finally:
            mod._dxcam_camera = old_camera

    def test_raises_when_frame_is_none(self):
        import windowspc_mcp.display.capture as mod
        old_camera = mod._dxcam_camera
        try:
            mock_camera = MagicMock()
            mock_camera.grab.return_value = None
            mod._dxcam_camera = mock_camera

            with pytest.raises(RuntimeError, match="dxcam returned None frame"):
                mod._capture_dxcam(0, 0, 200, 100)
        finally:
            mod._dxcam_camera = old_camera


# =========================================================================
# capture_region
# =========================================================================


class TestCaptureRegion:
    """Tests for capture_region: fallback chain and explicit backend selection."""

    def test_auto_uses_dxcam_first(self):
        import windowspc_mcp.display.capture as mod
        import numpy as np

        mock_dxcam_mod = MagicMock()
        old_camera = mod._dxcam_camera
        try:
            mock_camera = MagicMock()
            frame = np.zeros((100, 200, 3), dtype=np.uint8)
            mock_camera.grab.return_value = frame
            mod._dxcam_camera = mock_camera

            with patch.object(mod, "dxcam", mock_dxcam_mod):
                result = mod.capture_region(0, 0, 200, 100, backend="auto")
                assert isinstance(result, Image.Image)
        finally:
            mod._dxcam_camera = old_camera

    def test_auto_falls_back_to_mss_when_dxcam_none(self):
        import windowspc_mcp.display.capture as mod

        mock_sct = MagicMock()
        mock_shot = MagicMock()
        mock_shot.size = (200, 100)
        mock_shot.bgra = b"\x00" * (200 * 100 * 4)
        mock_sct.grab.return_value = mock_shot
        mock_mss_ctx = MagicMock()
        mock_mss_ctx.__enter__ = MagicMock(return_value=mock_sct)
        mock_mss_ctx.__exit__ = MagicMock(return_value=False)
        mock_mss_mod = MagicMock()
        mock_mss_mod.mss.return_value = mock_mss_ctx

        with patch.object(mod, "dxcam", None):
            with patch.object(mod, "mss_module", mock_mss_mod):
                result = mod.capture_region(0, 0, 200, 100, backend="auto")
                assert isinstance(result, Image.Image)

    def test_auto_falls_back_to_pillow_when_both_none(self):
        import windowspc_mcp.display.capture as mod

        mock_img = MagicMock(spec=Image.Image)
        with patch.object(mod, "dxcam", None):
            with patch.object(mod, "mss_module", None):
                with patch.object(mod, "ImageGrab") as mock_grab:
                    mock_grab.grab.return_value = mock_img
                    result = mod.capture_region(0, 0, 200, 100, backend="auto")
                    assert result is mock_img
                    mock_grab.grab.assert_called_once_with(
                        bbox=(0, 0, 200, 100), all_screens=True
                    )

    def test_explicit_pillow_backend(self):
        import windowspc_mcp.display.capture as mod

        mock_img = MagicMock(spec=Image.Image)
        with patch.object(mod, "ImageGrab") as mock_grab:
            mock_grab.grab.return_value = mock_img
            result = mod.capture_region(10, 20, 210, 120, backend="pillow")
            assert result is mock_img

    def test_explicit_mss_backend(self):
        import windowspc_mcp.display.capture as mod

        mock_sct = MagicMock()
        mock_shot = MagicMock()
        mock_shot.size = (200, 100)
        mock_shot.bgra = b"\x00" * (200 * 100 * 4)
        mock_sct.grab.return_value = mock_shot
        mock_mss_ctx = MagicMock()
        mock_mss_ctx.__enter__ = MagicMock(return_value=mock_sct)
        mock_mss_ctx.__exit__ = MagicMock(return_value=False)
        mock_mss_mod = MagicMock()
        mock_mss_mod.mss.return_value = mock_mss_ctx

        with patch.object(mod, "mss_module", mock_mss_mod):
            result = mod.capture_region(0, 0, 200, 100, backend="mss")
            assert isinstance(result, Image.Image)

    def test_all_backends_fail_falls_to_final_imagegrab(self):
        """When all chain backends fail, the final fallback ImageGrab.grab is used."""
        import windowspc_mcp.display.capture as mod

        mock_img = MagicMock(spec=Image.Image)

        old_camera = mod._dxcam_camera
        try:
            mock_camera = MagicMock()
            mock_camera.grab.side_effect = RuntimeError("dxcam fail")
            mod._dxcam_camera = mock_camera

            mock_dxcam = MagicMock()
            mock_mss = MagicMock()
            mock_mss.mss.side_effect = RuntimeError("mss fail")

            with patch.object(mod, "dxcam", mock_dxcam):
                with patch.object(mod, "mss_module", mock_mss):
                    with patch.object(mod, "ImageGrab") as mock_grab:
                        # First ImageGrab call (in pillow chain) fails, final fallback succeeds
                        mock_grab.grab.side_effect = [RuntimeError("pillow fail"), mock_img]
                        result = mod.capture_region(0, 0, 200, 100, backend="auto")
                        assert result is mock_img
        finally:
            mod._dxcam_camera = old_camera

    def test_unknown_backend_skips_to_final_fallback(self):
        """Unknown backend name results in no chain match, falls to final ImageGrab."""
        import windowspc_mcp.display.capture as mod

        mock_img = MagicMock(spec=Image.Image)
        with patch.object(mod, "ImageGrab") as mock_grab:
            mock_grab.grab.return_value = mock_img
            result = mod.capture_region(0, 0, 200, 100, backend="nonexistent")
            assert result is mock_img


# =========================================================================
# image_to_base64
# =========================================================================


class TestImageToBase64:
    """Tests for image_to_base64: normal, downscale, format."""

    def test_returns_data_uri_prefix(self):
        from windowspc_mcp.display.capture import image_to_base64

        img = Image.new("RGB", (100, 100), color=(255, 0, 0))
        result = image_to_base64(img)
        assert result.startswith("data:image/jpeg;base64,")

    def test_valid_base64_content(self):
        from windowspc_mcp.display.capture import image_to_base64

        img = Image.new("RGB", (100, 100), color=(0, 255, 0))
        result = image_to_base64(img)
        b64_part = result.split(",", 1)[1]
        decoded = base64.b64decode(b64_part)
        # Should be valid JPEG
        assert decoded[:2] == b"\xff\xd8"  # JPEG magic bytes

    def test_downscales_large_image(self):
        from windowspc_mcp.display.capture import image_to_base64

        img = Image.new("RGB", (3840, 2160), color=(0, 0, 255))
        result = image_to_base64(img, max_width=1920)
        # Decode and check the image was resized
        b64_part = result.split(",", 1)[1]
        decoded = base64.b64decode(b64_part)
        out_img = Image.open(io.BytesIO(decoded))
        assert out_img.width == 1920

    def test_no_downscale_when_within_limit(self):
        from windowspc_mcp.display.capture import image_to_base64

        img = Image.new("RGB", (800, 600), color=(128, 128, 128))
        result = image_to_base64(img, max_width=1920)
        b64_part = result.split(",", 1)[1]
        decoded = base64.b64decode(b64_part)
        out_img = Image.open(io.BytesIO(decoded))
        assert out_img.width == 800

    def test_custom_max_width(self):
        from windowspc_mcp.display.capture import image_to_base64

        img = Image.new("RGB", (2000, 1000), color=(0, 0, 0))
        result = image_to_base64(img, max_width=500)
        b64_part = result.split(",", 1)[1]
        decoded = base64.b64decode(b64_part)
        out_img = Image.open(io.BytesIO(decoded))
        assert out_img.width == 500
