"""Parsec VDD virtual display driver wrapper using ctypes DeviceIoControl."""

import ctypes
import ctypes.wintypes
import struct
import sys
import threading
import time
from ctypes import POINTER, byref, sizeof

# ---------------------------------------------------------------------------
# IOCTL codes
# ---------------------------------------------------------------------------
VDD_IOCTL_ADD = 0x0022E004
VDD_IOCTL_REMOVE = 0x0022A008
VDD_IOCTL_UPDATE = 0x0022A00C
VDD_IOCTL_VERSION = 0x0022E010

# ---------------------------------------------------------------------------
# Win32 constants
# ---------------------------------------------------------------------------
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x00000080
FILE_FLAG_NO_BUFFERING = 0x20000000
FILE_FLAG_OVERLAPPED = 0x40000000
FILE_FLAG_WRITE_THROUGH = 0x80000000
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

DIGCF_PRESENT = 0x00000002
DIGCF_DEVICEINTERFACE = 0x00000010

WAIT_TIMEOUT = 0x00000102
INFINITE = 0xFFFFFFFF
ERROR_IO_PENDING = 997

# ---------------------------------------------------------------------------
# Structures
# ---------------------------------------------------------------------------


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


# {00b41627-04c4-429e-a26e-0265cf50c8fa}
VDD_ADAPTER_GUID = GUID(
    Data1=0x00B41627,
    Data2=0x04C4,
    Data3=0x429E,
    Data4=(ctypes.c_ubyte * 8)(0xA2, 0x6E, 0x02, 0x65, 0xCF, 0x50, 0xC8, 0xFA),
)


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("InterfaceClassGuid", GUID),
        ("Flags", ctypes.c_ulong),
        ("Reserved", ctypes.POINTER(ctypes.c_ulong)),
    ]


class SP_DEVICE_INTERFACE_DETAIL_DATA_A(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("DevicePath", ctypes.c_char * 256),
    ]


class OVERLAPPED(ctypes.Structure):
    _fields_ = [
        ("Internal", ctypes.c_ulong),
        ("InternalHigh", ctypes.c_ulong),
        ("Offset", ctypes.c_ulong),
        ("OffsetHigh", ctypes.c_ulong),
        ("hEvent", ctypes.c_void_p),
    ]


# ---------------------------------------------------------------------------
# Win32 API bindings
# ---------------------------------------------------------------------------
_setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# setupapi
SetupDiGetClassDevsA = _setupapi.SetupDiGetClassDevsA
SetupDiGetClassDevsA.restype = ctypes.c_void_p
SetupDiGetClassDevsA.argtypes = [
    POINTER(GUID),          # ClassGuid
    ctypes.c_char_p,        # Enumerator
    ctypes.c_void_p,        # hwndParent
    ctypes.c_ulong,         # Flags
]

SetupDiEnumDeviceInterfaces = _setupapi.SetupDiEnumDeviceInterfaces
SetupDiEnumDeviceInterfaces.restype = ctypes.c_bool
SetupDiEnumDeviceInterfaces.argtypes = [
    ctypes.c_void_p,                        # DeviceInfoSet
    ctypes.c_void_p,                        # DeviceInfoData (optional)
    POINTER(GUID),                          # InterfaceClassGuid
    ctypes.c_ulong,                         # MemberIndex
    POINTER(SP_DEVICE_INTERFACE_DATA),      # DeviceInterfaceData
]

SetupDiGetDeviceInterfaceDetailA = _setupapi.SetupDiGetDeviceInterfaceDetailA
SetupDiGetDeviceInterfaceDetailA.restype = ctypes.c_bool
SetupDiGetDeviceInterfaceDetailA.argtypes = [
    ctypes.c_void_p,                                # DeviceInfoSet
    POINTER(SP_DEVICE_INTERFACE_DATA),              # DeviceInterfaceData
    POINTER(SP_DEVICE_INTERFACE_DETAIL_DATA_A),     # DeviceInterfaceDetailData
    ctypes.c_ulong,                                 # DeviceInterfaceDetailDataSize
    POINTER(ctypes.c_ulong),                        # RequiredSize
    ctypes.c_void_p,                                # DeviceInfoData (optional)
]

SetupDiDestroyDeviceInfoList = _setupapi.SetupDiDestroyDeviceInfoList
SetupDiDestroyDeviceInfoList.restype = ctypes.c_bool
SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]

# kernel32
CreateFileA = _kernel32.CreateFileA
CreateFileA.restype = ctypes.c_void_p
CreateFileA.argtypes = [
    ctypes.c_char_p,    # lpFileName
    ctypes.c_ulong,     # dwDesiredAccess
    ctypes.c_ulong,     # dwShareMode
    ctypes.c_void_p,    # lpSecurityAttributes
    ctypes.c_ulong,     # dwCreationDisposition
    ctypes.c_ulong,     # dwFlagsAndAttributes
    ctypes.c_void_p,    # hTemplateFile
]

DeviceIoControl = _kernel32.DeviceIoControl
DeviceIoControl.restype = ctypes.c_bool
DeviceIoControl.argtypes = [
    ctypes.c_void_p,        # hDevice
    ctypes.c_ulong,         # dwIoControlCode
    ctypes.c_void_p,        # lpInBuffer
    ctypes.c_ulong,         # nInBufferSize
    ctypes.c_void_p,        # lpOutBuffer
    ctypes.c_ulong,         # nOutBufferSize
    POINTER(ctypes.c_ulong),# lpBytesReturned
    POINTER(OVERLAPPED),    # lpOverlapped
]

CreateEventA = _kernel32.CreateEventA
CreateEventA.restype = ctypes.c_void_p
CreateEventA.argtypes = [
    ctypes.c_void_p,    # lpEventAttributes
    ctypes.c_bool,      # bManualReset
    ctypes.c_bool,      # bInitialState
    ctypes.c_char_p,    # lpName
]

GetOverlappedResultEx = _kernel32.GetOverlappedResultEx
GetOverlappedResultEx.restype = ctypes.c_bool
GetOverlappedResultEx.argtypes = [
    ctypes.c_void_p,        # hFile
    POINTER(OVERLAPPED),    # lpOverlapped
    POINTER(ctypes.c_ulong),# lpNumberOfBytesTransferred
    ctypes.c_ulong,         # dwMilliseconds
    ctypes.c_bool,          # bAlertable
]

CloseHandle = _kernel32.CloseHandle
CloseHandle.restype = ctypes.c_bool
CloseHandle.argtypes = [ctypes.c_void_p]


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def open_device_handle() -> int:
    """Open a handle to the Parsec VDD device via SetupDi enumeration.

    cbSize of SP_DEVICE_INTERFACE_DETAIL_DATA_A must be 8 on 64-bit and 5 on
    32-bit (it encodes sizeof(DWORD) + sizeof(TCHAR) in the header).

    Raises:
        OSError: if the Parsec VDD driver is not found or the handle cannot
                 be opened.

    Returns:
        int: An open Win32 file handle to the device.
    """
    guid = VDD_ADAPTER_GUID
    dev_info = SetupDiGetClassDevsA(
        byref(guid),
        None,
        None,
        DIGCF_PRESENT | DIGCF_DEVICEINTERFACE,
    )
    if dev_info == INVALID_HANDLE_VALUE or dev_info is None or dev_info == 0:
        raise OSError("Could not find Parsec VDD device info set")

    try:
        iface_data = SP_DEVICE_INTERFACE_DATA()
        iface_data.cbSize = sizeof(SP_DEVICE_INTERFACE_DATA)

        found = SetupDiEnumDeviceInterfaces(
            dev_info,
            None,
            byref(guid),
            0,
            byref(iface_data),
        )
        if not found:
            raise OSError("Could not find Parsec VDD device interface")

        detail = SP_DEVICE_INTERFACE_DETAIL_DATA_A()
        # On 64-bit Windows cbSize must be 8; on 32-bit it must be 5.
        detail.cbSize = 8 if sys.maxsize > 2**32 else 5

        SetupDiGetDeviceInterfaceDetailA(
            dev_info,
            byref(iface_data),
            byref(detail),
            sizeof(detail),
            None,
            None,
        )

        device_path = detail.DevicePath
        if not device_path:
            raise OSError("Could not find Parsec VDD")

        handle = CreateFileA(
            device_path,
            GENERIC_READ | GENERIC_WRITE,
            0,
            None,
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL | FILE_FLAG_NO_BUFFERING | FILE_FLAG_OVERLAPPED | FILE_FLAG_WRITE_THROUGH,
            None,
        )

        if handle == INVALID_HANDLE_VALUE or handle is None or handle == 0:
            raise OSError("Could not find Parsec VDD")

        return handle
    finally:
        SetupDiDestroyDeviceInfoList(dev_info)


def _vdd_ioctl(handle, code: int, data: bytes, data_size: int) -> int:
    """Send an IOCTL to the VDD device using overlapped I/O with a 5-second timeout.

    Args:
        handle: Open device handle.
        code:   IOCTL control code.
        data:   Input/output buffer (bytes or ctypes buffer).
        data_size: Size of the buffer.

    Returns:
        int: Number of bytes returned by the IOCTL.

    Raises:
        OSError: on timeout or I/O error.
    """
    event = CreateEventA(None, True, False, None)
    if event is None or event == 0:
        raise OSError("CreateEventA failed")

    try:
        overlapped = OVERLAPPED()
        overlapped.hEvent = event

        bytes_returned = ctypes.c_ulong(0)

        # Convert bytes to a writable ctypes buffer if needed
        if isinstance(data, (bytes, bytearray)):
            buf = (ctypes.c_char * len(data))(*data)
            buf_ptr = ctypes.cast(buf, ctypes.c_void_p)
        else:
            buf_ptr = ctypes.cast(data, ctypes.c_void_p)

        ok = DeviceIoControl(
            handle,
            code,
            buf_ptr,
            data_size,
            buf_ptr,
            data_size,
            byref(bytes_returned),
            byref(overlapped),
        )

        last_error = ctypes.get_last_error()
        if not ok and last_error != ERROR_IO_PENDING:
            raise OSError(f"DeviceIoControl failed with error {last_error}")

        transferred = ctypes.c_ulong(0)
        result = GetOverlappedResultEx(handle, byref(overlapped), byref(transferred), 5000, False)
        if not result:
            last_error = ctypes.get_last_error()
            if last_error == WAIT_TIMEOUT:
                raise OSError("VDD IOCTL timed out after 5 seconds")
            raise OSError(f"GetOverlappedResultEx failed with error {last_error}")

        return transferred.value
    finally:
        CloseHandle(event)


def vdd_add_display(handle) -> int:
    """Add a virtual display.

    Sends VDD_IOCTL_ADD and immediately pings the driver with VDD_IOCTL_UPDATE.

    Returns:
        int: Index of the newly added display.
    """
    buf = (ctypes.c_char * 4)(b'\x00', b'\x00', b'\x00', b'\x00')
    _vdd_ioctl(handle, VDD_IOCTL_ADD, buf, 4)
    index = buf[0]
    vdd_update(handle)
    return index


def vdd_remove_display(handle, index: int) -> None:
    """Remove a virtual display by index.

    The index is encoded as a 16-bit big-endian value in the buffer.

    Args:
        handle: Open device handle.
        index:  Display index to remove.
    """
    data = struct.pack(">H", index & 0xFFFF)
    buf = (ctypes.c_char * 2)(*data)
    _vdd_ioctl(handle, VDD_IOCTL_REMOVE, buf, 2)


def vdd_update(handle) -> None:
    """Send a keep-alive ping to the VDD driver."""
    buf = (ctypes.c_char * 4)(b'\x00', b'\x00', b'\x00', b'\x00')
    _vdd_ioctl(handle, VDD_IOCTL_UPDATE, buf, 4)


def vdd_version(handle) -> int:
    """Query the VDD driver version.

    Returns:
        int: Driver version as a 32-bit integer.
    """
    buf = (ctypes.c_char * 4)(b'\x00', b'\x00', b'\x00', b'\x00')
    _vdd_ioctl(handle, VDD_IOCTL_VERSION, buf, 4)
    return struct.unpack("<I", bytes(buf))[0]


# ---------------------------------------------------------------------------
# ParsecVDD class
# ---------------------------------------------------------------------------


class ParsecVDD:
    """High-level wrapper around the Parsec VDD driver.

    Opens a device handle on construction, starts a background keep-alive
    thread, and provides thread-safe methods to add/remove virtual displays.

    Usage::

        with ParsecVDD() as vdd:
            idx = vdd.add_display()
            ...
            # display is automatically removed on exit
    """

    _KEEPALIVE_INTERVAL = 0.050  # 50 ms

    def __init__(self) -> None:
        self._handle = open_device_handle()
        self._lock = threading.Lock()
        self._displays: list[int] = []
        self._stop_event = threading.Event()

        self._thread = threading.Thread(target=self._keepalive, daemon=True, name="vdd-keepalive")
        self._thread.start()

    # ------------------------------------------------------------------
    # Keep-alive thread
    # ------------------------------------------------------------------

    def _keepalive(self) -> None:
        """Background thread: send VDD_IOCTL_UPDATE every 50 ms."""
        while not self._stop_event.wait(self._KEEPALIVE_INTERVAL):
            try:
                vdd_update(self._handle)
            except OSError:
                # Silently ignore errors here; the main thread will surface
                # any real issues when it next calls an IOCTL.
                pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_display(self) -> int:
        """Add a virtual display and return its index (thread-safe)."""
        with self._lock:
            index = vdd_add_display(self._handle)
            self._displays.append(index)
            return index

    def remove_display(self, index: int) -> None:
        """Remove a virtual display by index (thread-safe)."""
        with self._lock:
            vdd_remove_display(self._handle, index)
            try:
                self._displays.remove(index)
            except ValueError:
                pass

    def remove_all(self) -> None:
        """Remove all displays created by this instance."""
        with self._lock:
            for index in list(self._displays):
                try:
                    vdd_remove_display(self._handle, index)
                except OSError:
                    pass
            self._displays.clear()

    def version(self) -> int:
        """Return the VDD driver version."""
        with self._lock:
            return vdd_version(self._handle)

    @property
    def active_displays(self) -> list[int]:
        """Return a copy of the list of active display indices."""
        with self._lock:
            return list(self._displays)

    def close(self) -> None:
        """Stop the keep-alive thread, remove all displays, and close the handle."""
        self._stop_event.set()
        self._thread.join(timeout=1.0)
        try:
            self.remove_all()
        except OSError:
            pass
        CloseHandle(self._handle)

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "ParsecVDD":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
