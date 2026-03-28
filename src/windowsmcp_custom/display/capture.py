"""Screen capture with fallback chain: dxcam -> mss -> Pillow."""

from __future__ import annotations

import base64
import io
import logging

from PIL import Image, ImageGrab

logger = logging.getLogger(__name__)

try:
    import dxcam
except ImportError:
    dxcam = None

try:
    import mss as mss_module
except ImportError:
    mss_module = None


def capture_region(left: int, top: int, right: int, bottom: int, backend: str = "auto") -> Image.Image:
    """Capture a screen region using the best available backend.

    Fallback chain: dxcam -> mss -> Pillow.
    """
    chain = ["dxcam", "mss", "pillow"] if backend == "auto" else [backend]
    for name in chain:
        try:
            if name == "dxcam" and dxcam is not None:
                camera = dxcam.create()
                frame = camera.grab(region=(left, top, right, bottom))
                if frame is None:
                    raise RuntimeError("None frame")
                return Image.fromarray(frame)
            elif name == "mss" and mss_module is not None:
                with mss_module.mss() as sct:
                    monitor = {
                        "left": left,
                        "top": top,
                        "width": right - left,
                        "height": bottom - top,
                    }
                    shot = sct.grab(monitor)
                    return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            elif name == "pillow":
                return ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)
        except Exception as e:
            logger.warning(f"Capture backend '{name}' failed: {e}")

    # Final fallback — should always work
    return ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)


def image_to_base64(image: Image.Image, max_width: int = 1920) -> str:
    """Convert a PIL Image to a base64-encoded JPEG data URI."""
    if image.width > max_width:
        ratio = max_width / image.width
        image = image.resize((max_width, int(image.height * ratio)), Image.LANCZOS)
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=85)
    return f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode('ascii')}"
