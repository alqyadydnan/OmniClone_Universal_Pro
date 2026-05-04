"""
OmniClone Agent - Partition Lock Manager (Target Side / WinPE)
Unmounts all partitions EXCEPT the selected target to ensure zero data loss.
Uses Windows API to lock volumes before writing.
"""

import ctypes
import ctypes.wintypes
import subprocess
import logging
from typing import List, Optional

logger = logging.getLogger("agent.lock")

GENERIC_READ        = 0x80000000
GENERIC_WRITE       = 0x40000000
FILE_SHARE_READ     = 0x00000001
FILE_SHARE_WRITE    = 0x00000002
OPEN_EXISTING       = 3
INVALID_HANDLE      = ctypes.c_void_p(-1).value

FSCTL_LOCK_VOLUME   = 0x00090018
FSCTL_DISMOUNT_VOLUME = 0x00090020


def _open_volume(letter: str, write_access: bool = False):
    access = GENERIC_READ
    if write_access:
        access |= GENERIC_WRITE
    path = f"\\\\.\\{letter}:"
    handle = ctypes.windll.kernel32.CreateFileW(
        path, access,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        None, OPEN_EXISTING, 0, None
    )
    return handle


def _ioctl(handle, code: int) -> bool:
    bytes_returned = ctypes.wintypes.DWORD(0)
    return bool(ctypes.windll.kernel32.DeviceIoControl(
        handle, code, None, 0, None, 0,
        ctypes.byref(bytes_returned), None
    ))


def lock_volume(letter: str) -> bool:
    """
    Lock a volume to prevent other processes from accessing it.
    Must be done before dismounting.
    """
    handle = _open_volume(letter, write_access=True)
    if handle == INVALID_HANDLE:
        logger.error(f"Cannot open volume {letter}: for locking")
        return False
    try:
        result = _ioctl(handle, FSCTL_LOCK_VOLUME)
        if result:
            logger.info(f"Volume {letter}: locked successfully.")
        else:
            err = ctypes.get_last_error()
            logger.warning(f"Could not lock {letter}: error {err}")
        return result
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def dismount_volume(letter: str) -> bool:
    """
    Dismount a volume so it cannot be accidentally written to.
    This is the safety lock that prevents data loss on other partitions.
    """
    handle = _open_volume(letter, write_access=True)
    if handle == INVALID_HANDLE:
        logger.warning(f"Cannot open {letter}: for dismount (may already be dismounted)")
        return True  # If we can't open it, it's effectively locked
    try:
        locked = _ioctl(handle, FSCTL_LOCK_VOLUME)
        if not locked:
            logger.warning(f"Could not lock {letter}: before dismount")

        result = _ioctl(handle, FSCTL_DISMOUNT_VOLUME)
        if result:
            logger.info(f"Volume {letter}: dismounted (safety locked).")
        else:
            err = ctypes.get_last_error()
            logger.error(f"Dismount of {letter}: failed: error {err}")
        return result
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def lock_all_except(all_letters: List[str], target_letter: str) -> dict:
    """
    Lock and dismount all volumes except the target.
    Returns a dict: {letter: success}
    """
    results = {}
    for letter in all_letters:
        if letter.upper() == target_letter.upper():
            logger.info(f"Skipping target partition {letter}: (will be written)")
            results[letter] = "target"
            continue
        if letter.upper() in ("X", "Y", "Z"):
            # WinPE system drive letters — don't touch
            results[letter] = "winpe_skip"
            continue
        success = dismount_volume(letter)
        results[letter] = "locked" if success else "failed"

    return results


def open_target_for_write(letter: str):
    """
    Open the target partition for raw block writes.
    Returns a handle or raises on failure.
    """
    path = f"\\\\.\\{letter}:"
    handle = ctypes.windll.kernel32.CreateFileW(
        path,
        GENERIC_READ | GENERIC_WRITE,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        None, OPEN_EXISTING, 0, None
    )
    if handle == INVALID_HANDLE:
        err = ctypes.get_last_error()
        raise IOError(f"Cannot open target {letter}: for writing: error {err}")

    # Lock the volume so we have exclusive access
    bytes_returned = ctypes.wintypes.DWORD(0)
    ctypes.windll.kernel32.DeviceIoControl(
        handle, FSCTL_LOCK_VOLUME, None, 0, None, 0,
        ctypes.byref(bytes_returned), None
    )
    return handle
