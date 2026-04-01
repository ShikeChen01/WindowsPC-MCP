"""Read-only viewer window that displays agent desktop frames on the user's desktop.

Renders BGRA pixel data from a :class:`FrameBuffer` via ``StretchDIBits``.
The viewer runs on a dedicated thread with its own Win32 message loop and uses
a timer-driven repaint cycle at the capture FPS.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import threading
from ctypes import POINTER

from windowspc_mcp.confinement.errors import InvalidStateError
from windowspc_mcp.desktop.capture import BITMAPINFO, BITMAPINFOHEADER, FrameBuffer

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Win32 constants
# ---------------------------------------------------------------------------

WM_PAINT = 0x000F
WM_TIMER = 0x0113
WM_CLOSE = 0x0010
WM_DESTROY = 0x0002
WM_QUIT = 0x0012

WS_OVERLAPPEDWINDOW = 0x00CF0000
CW_USEDEFAULT = 0x80000000

SW_SHOWNOACTIVATE = 4

HALFTONE = 4
DIB_RGB_COLORS = 0
BI_RGB = 0
SRCCOPY = 0x00CC0020

TIMER_ID = 1

# ---------------------------------------------------------------------------
# Win32 structures
# ---------------------------------------------------------------------------

LRESULT = ctypes.c_ssize_t

WNDPROC = ctypes.WINFUNCTYPE(
    LRESULT,                 # LRESULT (pointer-sized)
    ctypes.wintypes.HWND,    # hWnd
    ctypes.wintypes.UINT,    # uMsg
    ctypes.wintypes.WPARAM,  # wParam
    ctypes.wintypes.LPARAM,  # lParam
)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", ctypes.wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", ctypes.wintypes.HINSTANCE),
        ("hIcon", ctypes.wintypes.HICON),
        ("hCursor", ctypes.wintypes.HANDLE),
        ("hbrBackground", ctypes.wintypes.HANDLE),
        ("lpszMenuName", ctypes.wintypes.LPCWSTR),
        ("lpszClassName", ctypes.wintypes.LPCWSTR),
    ]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.wintypes.HWND),
        ("message", ctypes.wintypes.UINT),
        ("wParam", ctypes.wintypes.WPARAM),
        ("lParam", ctypes.wintypes.LPARAM),
        ("time", ctypes.wintypes.DWORD),
        ("pt", ctypes.wintypes.POINT),
    ]


class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [
        ("hdc", ctypes.wintypes.HDC),
        ("fErase", ctypes.wintypes.BOOL),
        ("rcPaint", ctypes.wintypes.RECT),
        ("fRestore", ctypes.wintypes.BOOL),
        ("fIncUpdate", ctypes.wintypes.BOOL),
        ("rgbReserved", ctypes.c_byte * 32),
    ]


# ---------------------------------------------------------------------------
# Win32 API bindings -- user32
# ---------------------------------------------------------------------------

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

# RegisterClassW(WNDCLASSW*) -> ATOM
user32.RegisterClassW.restype = ctypes.wintypes.ATOM
user32.RegisterClassW.argtypes = [POINTER(WNDCLASSW)]

# UnregisterClassW(LPCWSTR, HINSTANCE) -> BOOL
user32.UnregisterClassW.restype = ctypes.wintypes.BOOL
user32.UnregisterClassW.argtypes = [
    ctypes.wintypes.LPCWSTR,
    ctypes.wintypes.HINSTANCE,
]

# CreateWindowExW(...) -> HWND
user32.CreateWindowExW.restype = ctypes.wintypes.HWND
user32.CreateWindowExW.argtypes = [
    ctypes.wintypes.DWORD,      # dwExStyle
    ctypes.wintypes.LPCWSTR,    # lpClassName
    ctypes.wintypes.LPCWSTR,    # lpWindowName
    ctypes.wintypes.DWORD,      # dwStyle
    ctypes.c_int,               # x
    ctypes.c_int,               # y
    ctypes.c_int,               # nWidth
    ctypes.c_int,               # nHeight
    ctypes.wintypes.HWND,       # hWndParent
    ctypes.wintypes.HMENU,      # hMenu
    ctypes.wintypes.HINSTANCE,  # hInstance
    ctypes.c_void_p,            # lpParam
]

# DestroyWindow(HWND) -> BOOL
user32.DestroyWindow.restype = ctypes.wintypes.BOOL
user32.DestroyWindow.argtypes = [ctypes.wintypes.HWND]

# ShowWindow(HWND, int) -> BOOL
user32.ShowWindow.restype = ctypes.wintypes.BOOL
user32.ShowWindow.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]

# SetTimer(HWND, UINT_PTR, UINT, TIMERPROC) -> UINT_PTR
user32.SetTimer.restype = ctypes.wintypes.UINT
user32.SetTimer.argtypes = [
    ctypes.wintypes.HWND,
    ctypes.wintypes.UINT,
    ctypes.wintypes.UINT,
    ctypes.c_void_p,  # TIMERPROC (NULL — we use WM_TIMER)
]

# KillTimer(HWND, UINT_PTR) -> BOOL
user32.KillTimer.restype = ctypes.wintypes.BOOL
user32.KillTimer.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.UINT]

# GetMessageW(MSG*, HWND, UINT, UINT) -> int (not BOOL: returns -1, 0, or positive)
user32.GetMessageW.restype = ctypes.c_int
user32.GetMessageW.argtypes = [
    POINTER(MSG),
    ctypes.wintypes.HWND,
    ctypes.wintypes.UINT,
    ctypes.wintypes.UINT,
]

# TranslateMessage(MSG*) -> BOOL
user32.TranslateMessage.restype = ctypes.wintypes.BOOL
user32.TranslateMessage.argtypes = [POINTER(MSG)]

# DispatchMessageW(MSG*) -> LRESULT
user32.DispatchMessageW.restype = LRESULT
user32.DispatchMessageW.argtypes = [POINTER(MSG)]

# PostThreadMessageW(DWORD, UINT, WPARAM, LPARAM) -> BOOL
user32.PostThreadMessageW.restype = ctypes.wintypes.BOOL
user32.PostThreadMessageW.argtypes = [
    ctypes.wintypes.DWORD,
    ctypes.wintypes.UINT,
    ctypes.wintypes.WPARAM,
    ctypes.wintypes.LPARAM,
]

# BeginPaint(HWND, PAINTSTRUCT*) -> HDC
user32.BeginPaint.restype = ctypes.wintypes.HDC
user32.BeginPaint.argtypes = [ctypes.wintypes.HWND, POINTER(PAINTSTRUCT)]

# EndPaint(HWND, PAINTSTRUCT*) -> BOOL
user32.EndPaint.restype = ctypes.wintypes.BOOL
user32.EndPaint.argtypes = [ctypes.wintypes.HWND, POINTER(PAINTSTRUCT)]

# InvalidateRect(HWND, RECT*, BOOL) -> BOOL
user32.InvalidateRect.restype = ctypes.wintypes.BOOL
user32.InvalidateRect.argtypes = [
    ctypes.wintypes.HWND,
    ctypes.c_void_p,  # NULL = entire client area
    ctypes.wintypes.BOOL,
]

# GetClientRect(HWND, RECT*) -> BOOL
user32.GetClientRect.restype = ctypes.wintypes.BOOL
user32.GetClientRect.argtypes = [
    ctypes.wintypes.HWND,
    POINTER(ctypes.wintypes.RECT),
]

# DefWindowProcW(HWND, UINT, WPARAM, LPARAM) -> LRESULT
user32.DefWindowProcW.restype = LRESULT
user32.DefWindowProcW.argtypes = [
    ctypes.wintypes.HWND,
    ctypes.wintypes.UINT,
    ctypes.wintypes.WPARAM,
    ctypes.wintypes.LPARAM,
]

# PostQuitMessage(int) -> void
user32.PostQuitMessage.restype = None
user32.PostQuitMessage.argtypes = [ctypes.c_int]

# GetModuleHandleW(LPCWSTR) -> HMODULE
kernel32.GetModuleHandleW.restype = ctypes.wintypes.HMODULE
kernel32.GetModuleHandleW.argtypes = [ctypes.wintypes.LPCWSTR]

# GetCurrentThreadId() -> DWORD
kernel32.GetCurrentThreadId.restype = ctypes.wintypes.DWORD
kernel32.GetCurrentThreadId.argtypes = []

# ---------------------------------------------------------------------------
# Win32 API bindings -- gdi32
# ---------------------------------------------------------------------------

# StretchDIBits(HDC, int, int, int, int, int, int, int, int, void*, BITMAPINFO*, UINT, DWORD) -> int
gdi32.StretchDIBits.restype = ctypes.c_int
gdi32.StretchDIBits.argtypes = [
    ctypes.wintypes.HDC,    # hdc
    ctypes.c_int,           # xDest
    ctypes.c_int,           # yDest
    ctypes.c_int,           # wDest
    ctypes.c_int,           # hDest
    ctypes.c_int,           # xSrc
    ctypes.c_int,           # ySrc
    ctypes.c_int,           # wSrc
    ctypes.c_int,           # hSrc
    ctypes.c_void_p,        # lpBits
    ctypes.c_void_p,        # lpBmi (BITMAPINFO*)
    ctypes.wintypes.UINT,   # iUsage
    ctypes.wintypes.DWORD,  # dwRop
]

# SetStretchBltMode(HDC, int) -> int
gdi32.SetStretchBltMode.restype = ctypes.c_int
gdi32.SetStretchBltMode.argtypes = [ctypes.wintypes.HDC, ctypes.c_int]


# ---------------------------------------------------------------------------
# ViewerWindow
# ---------------------------------------------------------------------------


class ViewerWindow:
    """Read-only viewer that displays agent desktop frames on user's desktop.

    - Standard Win32 window with title bar and resize
    - Timer-driven repaint at capture FPS
    - Renders BGRA pixel data from FrameBuffer via StretchDIBits
    - View-only: no input forwarding, no click-through
    """

    WINDOW_CLASS_NAME = "WindowsPC_MCP_Viewer"
    DEFAULT_TITLE = "Agent Desktop Viewer"

    def __init__(self, frame_buffer: FrameBuffer, fps: int = 30) -> None:
        """
        Args:
            frame_buffer: Shared FrameBuffer from DesktopCapture.
            fps: Repaint rate (should match capture FPS).
        """
        if fps <= 0:
            raise ValueError("fps must be positive")

        self._frame_buffer = frame_buffer
        self._fps = fps

        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._hwnd: ctypes.wintypes.HWND | None = None
        self._ready = threading.Event()
        self._error: Exception | None = None

        # prevent GC of WNDPROC callback
        self._wndproc_ref: WNDPROC | None = None
        self._class_atom: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Create the viewer window and start the message pump.

        Runs on a dedicated thread (viewer needs its own message loop).

        Raises:
            InvalidStateError: If already running.
        """
        if self._thread is not None and self._thread.is_alive():
            raise InvalidStateError("ViewerWindow is already running")

        self._ready.clear()
        self._error = None

        self._thread = threading.Thread(
            target=self._viewer_main,
            name="ViewerWindow",
            daemon=True,
        )
        self._thread.start()

        # Wait for the viewer thread to finish setup.
        if not self._ready.wait(timeout=5.0):
            raise InvalidStateError(
                "ViewerWindow thread did not become ready within 5 seconds"
            )
        if self._error is not None:
            raise self._error

    def stop(self) -> None:
        """Destroy the window and stop the message pump. Idempotent."""
        if self._thread is None or not self._thread.is_alive():
            self._thread = None
            self._thread_id = None
            return

        # Send WM_QUIT to the viewer thread's message queue.
        if self._thread_id is not None:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)

        self._thread.join(timeout=5.0)
        self._thread = None
        self._thread_id = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def hwnd(self) -> int | None:
        return self._hwnd

    # ------------------------------------------------------------------
    # Viewer thread
    # ------------------------------------------------------------------

    def _viewer_main(self) -> None:
        """Entry point for the viewer daemon thread.

        1. Record the thread ID (for PostThreadMessageW).
        2. Register the window class.
        3. Create a standard overlapped window.
        4. ShowWindow(SW_SHOWNOACTIVATE).
        5. SetTimer for periodic repaint.
        6. Run message pump until WM_QUIT.
        7. Cleanup: KillTimer, DestroyWindow, UnregisterClassW.
        """
        self._thread_id = kernel32.GetCurrentThreadId()

        try:
            self._create_viewer_window()
        except Exception as exc:
            self._error = exc
            self._ready.set()
            self._cleanup()
            return

        # Signal that we're ready.
        self._ready.set()

        # -- message pump --
        self._msg = MSG()
        while True:
            ret = user32.GetMessageW(ctypes.byref(self._msg), None, 0, 0)
            if ret == 0 or ret == -1:
                # WM_QUIT (0) or error (-1) -- exit the loop.
                break
            user32.TranslateMessage(ctypes.byref(self._msg))
            user32.DispatchMessageW(ctypes.byref(self._msg))

        self._cleanup()

    def _create_viewer_window(self) -> None:
        """Register window class and create the viewer window."""
        hinstance = kernel32.GetModuleHandleW(None)

        self._wndproc_ref = WNDPROC(self._wndproc)

        wc = WNDCLASSW()
        wc.style = 0
        wc.lpfnWndProc = self._wndproc_ref
        wc.cbClsExtra = 0
        wc.cbWndExtra = 0
        wc.hInstance = hinstance
        wc.hIcon = None
        wc.hCursor = None
        wc.hbrBackground = None
        wc.lpszMenuName = None
        wc.lpszClassName = self.WINDOW_CLASS_NAME

        atom = user32.RegisterClassW(ctypes.byref(wc))
        if not atom:
            err = ctypes.get_last_error()
            if err != 1410:  # ERROR_CLASS_ALREADY_EXISTS
                raise InvalidStateError(
                    f"RegisterClassW failed for '{self.WINDOW_CLASS_NAME}', error {err}"
                )
        self._class_atom = atom

        width = self._frame_buffer.width or 800
        height = self._frame_buffer.height or 600

        hwnd = user32.CreateWindowExW(
            0,                          # dwExStyle
            self.WINDOW_CLASS_NAME,     # lpClassName
            self.DEFAULT_TITLE,         # lpWindowName
            WS_OVERLAPPEDWINDOW,        # dwStyle
            CW_USEDEFAULT,              # x
            CW_USEDEFAULT,              # y
            width,                      # nWidth
            height,                     # nHeight
            None,                       # hWndParent
            None,                       # hMenu
            hinstance,                  # hInstance
            None,                       # lpParam
        )
        if not hwnd:
            err = ctypes.get_last_error()
            raise InvalidStateError(
                f"CreateWindowExW failed for viewer window, error {err}"
            )
        self._hwnd = hwnd

        user32.ShowWindow(self._hwnd, SW_SHOWNOACTIVATE)

        # Set up repaint timer
        timer_interval_ms = max(1, 1000 // self._fps)
        user32.SetTimer(self._hwnd, TIMER_ID, timer_interval_ms, None)

        log.info(
            "Created viewer window (HWND %s, %dx%d @ %d fps, timer=%dms)",
            hwnd, width, height, self._fps, timer_interval_ms,
        )

    # ------------------------------------------------------------------
    # Window procedure
    # ------------------------------------------------------------------

    def _wndproc(
        self,
        hwnd: ctypes.wintypes.HWND,
        msg: int,
        wparam: int,
        lparam: int,
    ) -> int:
        """Window procedure dispatching messages."""
        if msg == WM_TIMER:
            user32.InvalidateRect(hwnd, None, False)
            return 0

        if msg == WM_PAINT:
            self._on_paint(hwnd)
            return 0

        if msg == WM_CLOSE:
            user32.DestroyWindow(hwnd)
            return 0

        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0

        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _on_paint(self, hwnd: ctypes.wintypes.HWND) -> None:
        """Render the latest frame from the FrameBuffer."""
        ps = PAINTSTRUCT()
        hdc = user32.BeginPaint(hwnd, ctypes.byref(ps))

        with self._frame_buffer.lock:
            data = self._frame_buffer.data
            width = self._frame_buffer.width
            height = self._frame_buffer.height

        if data:
            # Set up BITMAPINFO for the raw BGRA data
            bmi = BITMAPINFO()
            bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.bmiHeader.biWidth = width
            bmi.bmiHeader.biHeight = -height  # top-down
            bmi.bmiHeader.biPlanes = 1
            bmi.bmiHeader.biBitCount = 32
            bmi.bmiHeader.biCompression = BI_RGB

            # Get client rect for scaling
            client_rect = ctypes.wintypes.RECT()
            user32.GetClientRect(hwnd, ctypes.byref(client_rect))

            # Better quality when scaling
            gdi32.SetStretchBltMode(hdc, HALFTONE)

            # StretchDIBits scales the bitmap to fit the window
            gdi32.StretchDIBits(
                hdc,
                0, 0, client_rect.right, client_rect.bottom,   # dest
                0, 0, width, height,                            # src
                data,                                           # pixel bits
                ctypes.byref(bmi),                              # BITMAPINFO
                DIB_RGB_COLORS,                                 # usage
                SRCCOPY,                                        # rop
            )

        user32.EndPaint(hwnd, ctypes.byref(ps))

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def _cleanup(self) -> None:
        """KillTimer, DestroyWindow, UnregisterClassW."""
        if self._hwnd:
            user32.KillTimer(self._hwnd, TIMER_ID)
            user32.DestroyWindow(self._hwnd)
            self._hwnd = None
            log.debug("Destroyed viewer window")

        if self._class_atom:
            hinstance = kernel32.GetModuleHandleW(None)
            user32.UnregisterClassW(self.WINDOW_CLASS_NAME, hinstance)
            self._class_atom = 0

        self._wndproc_ref = None
