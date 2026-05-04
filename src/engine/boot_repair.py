"""
OmniClone Universal - Boot Repair
Detects BIOS/UEFI mode on target and runs bcdboot accordingly.
Triggered on the TARGET machine after the clone completes.
"""

import subprocess
import os
import ctypes
import logging
from typing import Tuple

logger = logging.getLogger("omniclone.boot_repair")


def is_uefi_system() -> bool:
    """
    Detect if the current system booted in UEFI mode.
    Checks for presence of EFI System Partition (ESP) via diskpart or firmware vars.
    """
    try:
        kernel32 = ctypes.windll.kernel32
        firmware_type = ctypes.c_uint(0)
        if hasattr(kernel32, "GetFirmwareType"):
            if kernel32.GetFirmwareType(ctypes.byref(firmware_type)):
                # 1 = BIOS, 2 = UEFI, 3 = Max
                return firmware_type.value == 2
    except Exception:
        pass

    # Fallback: check EFI variables directory via bcdedit
    try:
        r = subprocess.run(
            ["bcdedit", "/enum", "firmware"],
            capture_output=True, text=True, timeout=10
        )
        return r.returncode == 0 and "efi" in r.stdout.lower()
    except Exception:
        pass

    return False


def find_windows_directory(drive_letter: str) -> str:
    """Find the Windows directory on the cloned partition."""
    candidates = [
        f"{drive_letter}:\\Windows",
        f"{drive_letter}:\\windows",
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c
    return f"{drive_letter}:\\Windows"  # assume default


def find_efi_partition() -> str:
    """
    Find the EFI System Partition drive letter (or volume GUID).
    Uses diskpart to list partitions and find the ESP.
    """
    script = "list volume\r\n"
    result = subprocess.run(
        ["diskpart"],
        input=script, capture_output=True, text=True, timeout=15
    )
    for line in result.stdout.splitlines():
        if "System" in line or "EFI" in line or "FAT" in line:
            parts = line.split()
            for i, p in enumerate(parts):
                if len(p) == 1 and p.isalpha():
                    return p + ":"
    return "S:"  # conventional EFI letter


def assign_efi_letter(efi_letter: str = "S") -> bool:
    """
    Use diskpart to assign a drive letter to the EFI partition if it has none.
    """
    script = (
        "list disk\r\n"
        "select disk 0\r\n"
        "list partition\r\n"
        "select partition 1\r\n"
        f"assign letter={efi_letter}\r\n"
        "exit\r\n"
    )
    result = subprocess.run(
        ["diskpart"],
        input=script, capture_output=True, text=True, timeout=20
    )
    return result.returncode == 0


def run_boot_repair(target_drive: str, firmware_override: str = "auto") -> Tuple[bool, str]:
    """
    Run bcdboot to fix boot configuration on the cloned partition.

    Args:
        target_drive:      Drive letter of the cloned Windows partition (e.g. "C")
        firmware_override: "uefi", "bios", or "auto" (detect automatically)

    Returns:
        (success: bool, message: str)
    """
    if firmware_override == "auto":
        uefi = is_uefi_system()
    else:
        uefi = firmware_override.lower() == "uefi"

    mode = "UEFI" if uefi else "BIOS"
    logger.info(f"Boot repair: target drive={target_drive}: mode={mode}")

    windows_dir = find_windows_directory(target_drive)

    if uefi:
        # UEFI: need to write to EFI System Partition
        efi_letter = find_efi_partition()
        if efi_letter == "S:":
            assign_efi_letter("S")

        cmd = [
            "bcdboot",
            windows_dir,
            "/s", efi_letter,
            "/f", "UEFI",
            "/l", "ar-SA",  # Arabic locale for BCD
        ]
    else:
        # BIOS/MBR: write to the active partition's MBR
        cmd = [
            "bcdboot",
            windows_dir,
            "/s", f"{target_drive}:",
            "/f", "BIOS",
            "/l", "ar-SA",
        ]

    logger.info(f"Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            msg = f"Boot repair completed ({mode} mode). bcdboot: {result.stdout.strip()}"
            logger.info(msg)
            return True, msg
        else:
            msg = f"bcdboot failed (code {result.returncode}): {result.stderr.strip()}"
            logger.error(msg)
            return False, msg
    except FileNotFoundError:
        msg = "bcdboot.exe not found. Ensure Windows is installed on this WinPE environment."
        logger.error(msg)
        return False, msg
    except subprocess.TimeoutExpired:
        msg = "bcdboot timed out after 60 seconds."
        logger.error(msg)
        return False, msg
    except Exception as e:
        msg = f"Boot repair exception: {e}"
        logger.error(msg)
        return False, msg


def fix_mbr(disk_index: int = 0) -> Tuple[bool, str]:
    """
    Fix the MBR on a physical disk using bootrec.
    Used as a supplement to bcdboot for BIOS systems.
    """
    try:
        r = subprocess.run(
            ["bootrec", "/fixmbr"],
            capture_output=True, text=True, timeout=30
        )
        if r.returncode == 0:
            return True, "MBR fixed successfully."
        return False, f"bootrec /fixmbr failed: {r.stderr}"
    except Exception as e:
        return False, str(e)
