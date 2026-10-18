"""Windows handle-relative contract I/O; no path-based security fallback.

Native relative opens and identity checks are mechanical integrity controls.
Reparse points and hard links are rejected; open handles deny deletion and
files deny concurrent writes. No ACL, sandbox, or account policy is changed.
The sales-plan copy is kept byte-identical by a release regression.
"""

from __future__ import annotations

import ctypes
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from ctypes import wintypes as w
from pathlib import Path
from typing import Any

__all__ = ["Directory", "open_beneath"]


class _UnicodeString(ctypes.Structure):
    _fields_ = [("Length", w.USHORT), ("MaximumLength", w.USHORT), ("Buffer", w.LPWSTR)]


class _ObjectAttributes(ctypes.Structure):
    _fields_ = [
        ("Length", w.ULONG),
        ("RootDirectory", w.HANDLE),
        ("ObjectName", ctypes.POINTER(_UnicodeString)),
        ("Attributes", w.ULONG),
        ("SecurityDescriptor", w.LPVOID),
        ("SecurityQualityOfService", w.LPVOID),
    ]


class _IoStatus(ctypes.Structure):
    _fields_ = [("Status", ctypes.c_void_p), ("Information", ctypes.c_size_t)]


class _FileInfo(ctypes.Structure):
    _fields_ = [
        ("attributes", w.DWORD),
        ("creation", w.FILETIME),
        ("access", w.FILETIME),
        ("write", w.FILETIME),
        ("volume", w.DWORD),
        ("size_high", w.DWORD),
        ("size_low", w.DWORD),
        ("links", w.DWORD),
        ("index_high", w.DWORD),
        ("index_low", w.DWORD),
    ]


def _api() -> tuple[Any, Any]:
    if os.name != "nt":
        raise OSError("Windows native file handles are unavailable")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    native = ctypes.WinDLL("ntdll")
    kernel.CreateFileW.argtypes = [
        w.LPCWSTR,
        w.DWORD,
        w.DWORD,
        w.LPVOID,
        w.DWORD,
        w.DWORD,
        w.HANDLE,
    ]
    kernel.CreateFileW.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.CloseHandle.restype = w.BOOL
    kernel.GetFileInformationByHandle.argtypes = [w.HANDLE, ctypes.POINTER(_FileInfo)]
    kernel.GetFileInformationByHandle.restype = w.BOOL
    kernel.SetFileInformationByHandle.argtypes = [
        w.HANDLE,
        ctypes.c_int,
        w.LPVOID,
        w.DWORD,
    ]
    kernel.SetFileInformationByHandle.restype = w.BOOL
    native.NtCreateFile.argtypes = [
        ctypes.POINTER(w.HANDLE),
        w.DWORD,
        ctypes.POINTER(_ObjectAttributes),
        ctypes.POINTER(_IoStatus),
        w.LPVOID,
        w.ULONG,
        w.ULONG,
        w.ULONG,
        w.ULONG,
        w.LPVOID,
        w.ULONG,
    ]
    native.NtCreateFile.restype = w.LONG
    native.RtlNtStatusToDosError.argtypes = [w.LONG]
    native.RtlNtStatusToDosError.restype = w.ULONG
    return kernel, native


def _info(handle: int) -> _FileInfo:
    kernel, _ = _api()
    value = _FileInfo()
    if not kernel.GetFileInformationByHandle(handle, ctypes.byref(value)):
        raise ctypes.WinError(ctypes.get_last_error())
    if value.attributes & 0x400:  # FILE_ATTRIBUTE_REPARSE_POINT
        raise OSError("Reparse points are not permitted in contract paths")
    return value


def _identity(handle: int) -> tuple[int, int, int]:
    info = _info(handle)
    return info.volume, (info.index_high << 32) | info.index_low, stat.S_IFDIR


def _close(handle: int) -> None:
    kernel, _ = _api()
    kernel.CloseHandle(handle)


def _component(name: str) -> None:
    # Reject NT namespaces, alternate streams, traversal, and Win32 aliases.
    if (
        not name
        or name in {".", ".."}
        or any(c in name for c in "\\/:\0")
        or name.endswith((".", " "))
    ):
        raise OSError("Expected one ordinary Windows path component")


def _relative(
    parent: int,
    name: str,
    *,
    directory: bool = False,
    create: bool = False,
    delete: bool = False,
) -> int:
    _component(name)
    _, native = _api()
    buffer = ctypes.create_unicode_buffer(name)
    size = len(name.encode("utf-16-le"))
    text = _UnicodeString(size, size + 2, ctypes.cast(buffer, w.LPWSTR))
    attrs = _ObjectAttributes(
        ctypes.sizeof(_ObjectAttributes), parent, ctypes.pointer(text), 0x40, None, None
    )
    status = _IoStatus()
    result = w.HANDLE()
    # FILE_LIST_DIRECTORY participates in sharing checks; attributes-only
    # handles do not prevent another handle from renaming the directory.
    access = 0x100081 if directory else (0x12019F if create else 0x120089)
    if delete:
        access |= 0x10000
    options = 0x200000 | 0x20 | (1 if directory else 0x40)
    code = native.NtCreateFile(
        ctypes.byref(result),
        access,
        ctypes.byref(attrs),
        ctypes.byref(status),
        None,
        0x80,
        3 if directory else 1,
        2 if create else 1,
        options,
        None,
        0,
    )
    if code < 0:
        raise ctypes.WinError(native.RtlNtStatusToDosError(code))
    handle = int(result.value)
    try:
        info = _info(handle)
        if bool(info.attributes & 0x10) != directory:
            raise OSError("Contract path has the wrong file type")
        if not directory and info.links != 1:
            raise OSError("Contract file must have exactly one hard link")
    except BaseException:
        _close(handle)
        raise
    return handle


class Directory:
    """Pin an actual directory and open children relative to its native handle."""

    def __init__(self, path: Path, *, parent: Directory | None = None) -> None:
        self.path = Path(path).absolute()
        kernel, _ = _api()
        if parent is None:
            handle = kernel.CreateFileW(
                str(self.path), 0x100081, 3, None, 3, 0x02000000 | 0x00200000, None
            )
            if handle == ctypes.c_void_p(-1).value:
                raise ctypes.WinError(ctypes.get_last_error())
            self.handle = int(handle)
        else:
            self.handle = _relative(parent.handle, self.path.name, directory=True)
        try:
            if not _info(self.handle).attributes & 0x10:
                raise OSError("Expected a real directory")
            self.identity = _identity(self.handle)
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        if self.handle is not None:
            _close(self.handle)
            self.handle = None

    def verify(self) -> None:
        with directory(self.path) as current:
            if (
                current.identity != self.identity
                or _identity(self.handle) != self.identity
            ):
                raise OSError("Pinned directory path identity changed")

    def open(self, name: str, *, create: bool = False) -> int:
        import msvcrt

        self.verify()
        handle = _relative(self.handle, name, create=create)
        try:
            return msvcrt.open_osfhandle(
                handle, os.O_BINARY | (os.O_RDWR if create else os.O_RDONLY)
            )
        except BaseException:
            _close(handle)
            raise

    def stat(self, name: str) -> os.stat_result:
        descriptor = self.open(name)
        try:
            return os.fstat(descriptor)
        finally:
            os.close(descriptor)

    def unlink(self, name: str, expected: tuple[int, int, int]) -> None:
        import msvcrt

        self.verify()
        handle = _relative(self.handle, name, delete=True)
        try:
            descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
        except BaseException:
            _close(handle)
            raise
        try:
            current = os.fstat(descriptor)
            if (
                current.st_dev,
                current.st_ino,
                stat.S_IFMT(current.st_mode),
            ) != expected:
                raise OSError("Partial output identity changed")
            kernel, _ = _api()
            disposition = ctypes.c_ubyte(1)
            if not kernel.SetFileInformationByHandle(
                handle, 4, ctypes.byref(disposition), 1
            ):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            os.close(descriptor)


@contextmanager
def directory(path: Path, *, parent: Directory | None = None) -> Iterator[Directory]:
    value = Directory(path, parent=parent)
    try:
        yield value
    finally:
        value.close()


@contextmanager
def open_beneath(root: Path, parts: tuple[str, ...]) -> Iterator[int]:
    directories: list[Directory] = []
    descriptor: int | None = None
    try:
        current = Directory(root)
        directories.append(current)
        for part in parts[:-1]:
            current = Directory(current.path / part, parent=current)
            directories.append(current)
        descriptor = current.open(parts[-1])
        before = os.fstat(descriptor)
        yield descriptor
        after = os.fstat(descriptor)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_nlink)
        if identity(before) != identity(after) or identity(after) != identity(
            current.stat(parts[-1])
        ):
            raise OSError("Contract input changed during reading")
        for entry in directories:
            entry.verify()
    finally:
        if descriptor is not None:
            os.close(descriptor)
        for entry in reversed(directories):
            entry.close()
