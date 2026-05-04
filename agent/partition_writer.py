"""
OmniClone Agent - Partition Writer (Target Side / WinPE)
Receives compressed blocks from source and writes them to the target partition.
Verifies MD5 checksums on every block.
"""

import ctypes
import ctypes.wintypes
import struct
import logging
from typing import Optional, Callable

try:
    import lz4.frame as lz4
except ImportError:
    lz4 = None

from .lock_manager import open_target_for_write
from ..src.protocol.messages import compute_md5

logger = logging.getLogger("agent.writer")

BYTES_PER_SECTOR = 512
INVALID_HANDLE   = ctypes.c_void_p(-1).value


def _seek(handle, offset: int):
    kernel32 = ctypes.windll.kernel32
    offset_high = ctypes.wintypes.LONG(offset >> 32)
    offset_low  = ctypes.wintypes.LONG(offset & 0xFFFFFFFF)
    result = kernel32.SetFilePointer(handle, offset_low, ctypes.byref(offset_high), 0)
    if result == 0xFFFFFFFF:
        err = ctypes.get_last_error()
        if err != 0:
            raise IOError(f"Seek to {offset} failed: error {err}")


def _write_raw(handle, data: bytes) -> int:
    kernel32 = ctypes.windll.kernel32
    buf = ctypes.create_string_buffer(data)
    bytes_written = ctypes.wintypes.DWORD(0)
    ret = kernel32.WriteFile(handle, buf, len(data), ctypes.byref(bytes_written), None)
    if not ret:
        err = ctypes.get_last_error()
        raise IOError(f"WriteFile failed: error {err}")
    return bytes_written.value


def _decompress(data: bytes) -> bytes:
    if lz4 is None:
        return data
    return lz4.decompress(data)


class PartitionWriter:
    """
    Writes received blocks to the target partition.
    Verifies MD5 on each block before writing.
    """

    def __init__(self, target_letter: str,
                 partition_offset: int = 0,
                 on_progress: Optional[Callable[[int, int], None]] = None):
        self.target_letter    = target_letter
        self.partition_offset = partition_offset  # bytes from start of disk to partition
        self.on_progress      = on_progress
        self._handle          = None
        self._bytes_written   = 0
        self._blocks_written  = 0

    def open(self):
        self._handle = open_target_for_write(self.target_letter)
        logger.info(f"Target volume {self.target_letter}: opened for writing.")

    def close(self):
        if self._handle and self._handle != INVALID_HANDLE:
            # Flush buffers before closing
            ctypes.windll.kernel32.FlushFileBuffers(self._handle)
            ctypes.windll.kernel32.CloseHandle(self._handle)
            self._handle = None
            logger.info(f"Target volume {self.target_letter}: closed and flushed.")

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *_):
        self.close()

    def write_block(self, offset: int, compressed_data: bytes,
                    original_size: int, expected_md5: str) -> tuple:
        """
        Decompress and write one block.
        Returns (success: bool, actual_md5: str)
        """
        raw = _decompress(compressed_data)

        if len(raw) != original_size:
            return False, f"Size mismatch: expected {original_size}, got {len(raw)}"

        actual_md5 = compute_md5(raw)
        if actual_md5 != expected_md5:
            logger.error(f"MD5 mismatch at offset {offset}: expected={expected_md5}, got={actual_md5}")
            return False, actual_md5

        # Align write to sector boundary
        aligned_size = ((len(raw) + BYTES_PER_SECTOR - 1) // BYTES_PER_SECTOR) * BYTES_PER_SECTOR
        if len(raw) < aligned_size:
            raw = raw + b"\x00" * (aligned_size - len(raw))

        _seek(self._handle, offset)
        written = _write_raw(self._handle, raw)

        self._bytes_written  += original_size
        self._blocks_written += 1

        if self.on_progress:
            self.on_progress(self._bytes_written, self._blocks_written)

        return True, actual_md5
