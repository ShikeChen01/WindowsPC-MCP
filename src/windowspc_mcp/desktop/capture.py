"""Frame capture from the agent's Win32 desktop via BitBlt.

When the user is on their own desktop (AGENT_SOLO mode), the agent desktop is
not the thread's desktop.  This module spawns a dedicated capture thread that
calls ``SetThreadDesktop(agent_desktop_handle)`` and then uses GDI BitBlt to
copy pixels from the desktop DC into a shared :class:`FrameBuffer`.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import threading
import time
from dataclasses import dataclass, field

from windowspc_mcp.confinement.errors import InvalidStateError

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Win32 constants
# ---------------------------------------------------------------------------

SRCCOPY = 0x00CC0020
DIB_RGB_COLORS = 0
BI_RGB = 0

# ---------------------------------------------------------------------------
# Win32 API bindings — user32
# ---------------------------------------------------------------------------

user32 = ctypes.WinDLL("user32", use_last_error=True)

# HDC GetDC(HWND)
user32.GetDC.restype = ctypes.wintypes.HDC
user32.GetDC.argtypes = [ctypes.wintypes.HWND]

# int ReleaseDC(HWND, HDC)
user32.ReleaseDC.restype = ctypes.c_int
user32.ReleaseDC.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.HDC]

# BOOL SetThreadDesktop(HDESK)
user32.SetThreadDesktop.restype = ctypes.wintypes.BOOL
user32.SetThreadDesktop.argtypes = [ctypes.wintypes.HANDLE]

# int GetSystemMetrics(int)
user32.GetSystemMetrics.restype = ctypes.c_int
user32.GetSystemMetrics.argtypes = [ctypes.c_int]

# ---------------------------------------------------------------------------
# Win32 API bindings — gdi32
# ---------------------------------------------------------------------------

gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

# HDC CreateCompatibleDC(HDC)
gdi32.CreateCompatibleDC.restype = ctypes.wintypes.HDC
gdi32.CreateCompatibleDC.argtypes = [ctypes.wintypes.HDC]

# HBITMAP CreateCompatibleBitmap(HDC, int, int)
gdi32.CreateCompatibleBitmap.restype = ctypes.wintypes.HBITMAP
gdi32.CreateCompatibleBitmap.argtypes = [
    ctypes.wintypes.HDC,
    ctypes.c_int,
    ctypes.c_int,
]

# HGDIOBJ SelectObject(HDC, HGDIOBJ)
gdi32.SelectObject.restype = ctypes.wintypes.HGDIOBJ
gdi32.SelectObject.argtypes = [ctypes.wintypes.HDC, ctypes.wintypes.HGDIOBJ]

# BOOL BitBlt(HDC, int, int, int, int, HDC, int, int, DWORD)
gdi32.BitBlt.restype = ctypes.wintypes.BOOL
gdi32.BitBlt.argtypes = [
    ctypes.wintypes.HDC,    # hdcDest
    ctypes.c_int,           # x
    ctypes.c_int,           # y
    ctypes.c_int,           # cx (width)
    ctypes.c_int,           # cy (height)
    ctypes.wintypes.HDC,    # hdcSrc
    ctypes.c_int,           # x1
    ctypes.c_int,           # y1
    ctypes.wintypes.DWORD,  # rop
]

# int GetDIBits(HDC, HBITMAP, UINT, UINT, LPVOID, BITMAPINFO*, UINT)
gdi32.GetDIBits.restype = ctypes.c_int
gdi32.GetDIBits.argtypes = [
    ctypes.wintypes.HDC,
    ctypes.wintypes.HBITMAP,
    ctypes.wintypes.UINT,
    ctypes.wintypes.UINT,
    ctypes.c_void_p,
    ctypes.c_void_p,        # pointer to BITMAPINFO
    ctypes.wintypes.UINT,
]

# BOOL DeleteObject(HGDIOBJ)
gdi32.DeleteObject.restype = ctypes.wintypes.BOOL
gdi32.DeleteObject.argtypes = [ctypes.wintypes.HGDIOBJ]

# BOOL DeleteDC(HDC)
gdi32.DeleteDC.restype = ctypes.wintypes.BOOL
gdi32.DeleteDC.argtypes = [ctypes.wintypes.HDC]


# ---------------------------------------------------------------------------
# GDI structures
# ---------------------------------------------------------------------------

class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.c_ulong),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),        # Negative = top-down
        ("biPlanes", ctypes.c_ushort),
        ("biBitCount", ctypes.c_ushort),
        ("biCompression", ctypes.c_ulong),
        ("biSizeImage", ctypes.c_ulong),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", ctypes.c_ulong),
        ("biClrImportant", ctypes.c_ulong),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", BITMAPINFOHEADER),
        ("bmiColors", ctypes.c_ulong * 1),  # unused for 32bpp
    ]


# ---------------------------------------------------------------------------
# FrameBuffer
# ---------------------------------------------------------------------------

@dataclass
class FrameBuffer:
    """Shared frame data between capture thread and viewer."""

    width: int = 0
    height: int = 0
    data: bytes = b""          # Raw BGRA pixel data
    timestamp_ns: int = 0      # When this frame was captured
    lock: threading.Lock = field(default_factory=threading.Lock)


# ---------------------------------------------------------------------------
# DesktopCapture
# ---------------------------------------------------------------------------

class DesktopCapture:
    """Captures frames from the agent desktop via BitBlt.

    Runs a capture thread that:

    1. Calls ``SetThreadDesktop(agent_desktop_handle)``
    2. Gets the desktop DC via ``GetDC(NULL)``
    3. Creates a compatible memory DC and bitmap
    4. BitBlts from desktop DC to memory DC
    5. Copies pixel data to shared :class:`FrameBuffer`
    """

    DEFAULT_FPS = 30

    def __init__(
        self,
        desktop_handle: int,
        width: int,
        height: int,
        fps: int = DEFAULT_FPS,
    ) -> None:
        """
        Args:
            desktop_handle: HDESK handle from DesktopManager._agent_desktop
            width: Capture width in pixels (should match VDD resolution)
            height: Capture height in pixels (should match VDD resolution)
            fps: Target capture framerate
        """
        self._desktop_handle = desktop_handle
        self._width = width
        self._height = height
        self._fps = fps

        self._frame_buffer = FrameBuffer(width=width, height=height)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

        # FPS tracking
        self._frame_timestamps: list[float] = []
        self._fps_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the capture thread.

        Raises:
            InvalidStateError: If already running.
        """
        if self._thread is not None and self._thread.is_alive():
            raise InvalidStateError("Capture is already running")

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._capture_loop,
            name="DesktopCapture",
            daemon=True,
        )
        self._thread.start()
        log.info(
            "Started desktop capture thread (%dx%d @ %d fps)",
            self._width,
            self._height,
            self._fps,
        )

    def stop(self) -> None:
        """Stop the capture thread.  Idempotent."""
        if self._thread is None or not self._thread.is_alive():
            return
        self._stop_event.set()
        self._thread.join(timeout=5)
        if self._thread.is_alive():
            log.warning("Capture thread did not terminate within 5 s")
        self._thread = None
        log.info("Stopped desktop capture thread")

    def get_frame(self) -> FrameBuffer:
        """Get the latest captured frame.  Thread-safe read from shared buffer.

        Returns a *snapshot* — the caller gets a consistent copy of width,
        height, data, and timestamp that won't change under them.
        """
        with self._frame_buffer.lock:
            return FrameBuffer(
                width=self._frame_buffer.width,
                height=self._frame_buffer.height,
                data=self._frame_buffer.data,
                timestamp_ns=self._frame_buffer.timestamp_ns,
            )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def fps(self) -> int:
        return self._fps

    @property
    def actual_fps(self) -> float:
        """Measured FPS over the last second."""
        now = time.perf_counter()
        with self._fps_lock:
            # Prune timestamps older than 1 second
            self._frame_timestamps = [
                t for t in self._frame_timestamps if now - t <= 1.0
            ]
            return float(len(self._frame_timestamps))

    # ------------------------------------------------------------------
    # Capture loop (runs on dedicated thread)
    # ------------------------------------------------------------------

    def _capture_loop(self) -> None:
        """Main capture loop — runs on the dedicated capture thread."""
        # 1. Attach to agent desktop
        if not user32.SetThreadDesktop(self._desktop_handle):
            err = ctypes.get_last_error()
            log.error("SetThreadDesktop failed, error %d", err)
            return

        # 2. Get desktop DC (NULL = entire desktop)
        hdc_desktop = user32.GetDC(None)
        if not hdc_desktop:
            log.error("GetDC(NULL) failed, error %d", ctypes.get_last_error())
            return

        # 3. Create memory DC and bitmap
        hdc_mem = gdi32.CreateCompatibleDC(hdc_desktop)
        if not hdc_mem:
            log.error(
                "CreateCompatibleDC failed, error %d", ctypes.get_last_error()
            )
            user32.ReleaseDC(None, hdc_desktop)
            return

        hbm = gdi32.CreateCompatibleBitmap(
            hdc_desktop, self._width, self._height
        )
        if not hbm:
            log.error(
                "CreateCompatibleBitmap failed, error %d",
                ctypes.get_last_error(),
            )
            gdi32.DeleteDC(hdc_mem)
            user32.ReleaseDC(None, hdc_desktop)
            return

        gdi32.SelectObject(hdc_mem, hbm)

        # 4. Prepare BITMAPINFO for GetDIBits
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = self._width
        bmi.bmiHeader.biHeight = -self._height  # negative = top-down
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = BI_RGB

        pixel_buf = ctypes.create_string_buffer(self._width * self._height * 4)

        # 5. Capture loop
        try:
            while not self._stop_event.is_set():
                frame_start = time.perf_counter_ns()

                # BitBlt from desktop to memory DC
                gdi32.BitBlt(
                    hdc_mem,
                    0,
                    0,
                    self._width,
                    self._height,
                    hdc_desktop,
                    0,
                    0,
                    SRCCOPY,
                )

                # Extract pixels
                gdi32.GetDIBits(
                    hdc_mem,
                    hbm,
                    0,
                    self._height,
                    pixel_buf,
                    ctypes.byref(bmi),
                    DIB_RGB_COLORS,
                )

                # Write to shared buffer under lock
                with self._frame_buffer.lock:
                    self._frame_buffer.data = bytes(pixel_buf)
                    self._frame_buffer.timestamp_ns = time.perf_counter_ns()

                # Record frame timestamp for actual_fps
                now = time.perf_counter()
                with self._fps_lock:
                    self._frame_timestamps.append(now)
                    # Keep only timestamps within the last second
                    self._frame_timestamps = [
                        t for t in self._frame_timestamps if now - t <= 1.0
                    ]

                # FPS throttle
                elapsed = (time.perf_counter_ns() - frame_start) / 1_000_000_000
                sleep_time = (1.0 / self._fps) - elapsed
                if sleep_time > 0:
                    self._stop_event.wait(sleep_time)
        except Exception:
            log.exception("Capture loop crashed")
        finally:
            # 6. Cleanup GDI objects
            gdi32.DeleteObject(hbm)
            gdi32.DeleteDC(hdc_mem)
            user32.ReleaseDC(None, hdc_desktop)
            log.debug("Capture loop cleaned up GDI resources")
