"""Screen capture with fallback chain: dxcam -> mss -> Pillow."""

from __future__ import annotations

import base64
import concurrent.futures
import io
import logging

from PIL import Image, ImageGrab

logger = logging.getLogger(__name__)

try:
    import dxcam
except ImportError:
    dxcam = None

# dxcam.create() can hang in threadpool workers (COM threading issue).
# Disable it for now — mss/pillow fallback works reliably for VDD captures.
dxcam = None

# Module-level camera cache
_dxcam_camera = None

try:
    import mss as mss_module
except ImportError:
    mss_module = None


def _capture_dxcam(left: int, top: int, right: int, bottom: int) -> Image.Image:
    """Capture using cached dxcam camera."""
    global _dxcam_camera
    if _dxcam_camera is None:
        _dxcam_camera = dxcam.create()
    frame = _dxcam_camera.grab(region=(left, top, right, bottom))
    if frame is None:
        raise RuntimeError("dxcam returned None frame")
    return Image.fromarray(frame)


def capture_region(left: int, top: int, right: int, bottom: int, backend: str = "auto") -> Image.Image:
    """Capture a screen region using the best available backend.

    Fallback chain: dxcam -> mss -> Pillow.
    """
    # mss can hang in anyio threadpool workers. Use pillow only for reliability.
    chain = ["pillow"] if backend == "auto" else [backend]
    for name in chain:
        try:
            if name == "dxcam" and dxcam is not None:
                return _capture_dxcam(left, top, right, bottom)
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


# Dedicated thread pool for GDI capture — avoids hangs in anyio's threadpool
# where COM apartment state can interfere with GDI/BitBlt calls.
_capture_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="capture")


def capture_region_safe(left: int, top: int, right: int, bottom: int) -> Image.Image:
    """Capture a screen region using a dedicated thread (GDI-safe).

    Use this instead of capture_region when calling from async/threadpool contexts
    (e.g., FastMCP tool handlers) where GDI calls may hang.
    """
    future = _capture_executor.submit(capture_region, left, top, right, bottom)
    return future.result(timeout=10)


def image_to_base64(image: Image.Image, max_width: int = 1920, quality: int = 85) -> str:
    """Convert a PIL Image to raw base64-encoded JPEG (no data URI prefix)."""
    if image.width > max_width:
        ratio = max_width / image.width
        image = image.resize((max_width, int(image.height * ratio)), Image.LANCZOS)
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode('ascii')
