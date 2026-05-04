"""
OmniClone Agent - Partition Scanner (Target Side / WinPE)
Enumerates all partitions on the target machine and reports them.
"""

import subprocess
import json
import logging
from typing import List

logger = logging.getLogger("agent.scanner")


def scan_partitions():
    """
    Scan all partitions on the target machine.
    Returns a list of partition dicts compatible with PartitionInfo.
    Works within WinPE which may not have full WMI available.
    Uses diskpart + PowerShell fallback.
    """
    partitions = []

    try:
        partitions = _scan_via_powershell()
        if partitions:
            return partitions
    except Exception as e:
        logger.warning(f"PowerShell scan failed: {e}, trying diskpart...")

    try:
        partitions = _scan_via_diskpart()
    except Exception as e:
        logger.error(f"Diskpart scan also failed: {e}")

    return partitions


def _scan_via_powershell() -> List[dict]:
    """Use PowerShell + WMI to enumerate partitions (preferred)."""
    ps_script = r"""
$result = @()
$disks = Get-WmiObject Win32_DiskDrive
foreach ($disk in $disks) {
    $partitions = Get-WmiObject -Query "ASSOCIATORS OF {Win32_DiskDrive.DeviceID='$($disk.DeviceID -replace '\\\\','\\\\')' } WHERE AssocClass=Win32_DiskDriveToDiskPartition"
    foreach ($part in $partitions) {
        $logicals = Get-WmiObject -Query "ASSOCIATORS OF {Win32_DiskPartition.DeviceID='$($part.DeviceID)'} WHERE AssocClass=Win32_LogicalDiskToPartition"
        foreach ($ld in $logicals) {
            $vol = Get-WmiObject Win32_Volume | Where-Object { $_.DriveLetter -eq $ld.DeviceID }
            $letter = $ld.DeviceID.TrimEnd(':').TrimEnd('\\')
            $result += [PSCustomObject]@{
                letter          = $letter
                label           = if ($ld.VolumeName) { $ld.VolumeName } else { '' }
                fs              = if ($ld.FileSystem) { $ld.FileSystem } else { 'Unknown' }
                size_bytes      = [long]$ld.Size
                used_bytes      = [long]$ld.Size - [long]$ld.FreeSpace
                device_path     = "\\\\.\\" + $letter + ":"
                partition_index = [int]$part.Index
                disk_index      = [int]$disk.Index
                offset_bytes    = [long]$part.StartingOffset
                is_system       = ($ld.DeviceID -eq 'C:')
                is_active       = $false
            }
        }
    }
}
$result | ConvertTo-Json -Depth 3
"""
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive",
         "-ExecutionPolicy", "Bypass", "-Command", ps_script],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        raise RuntimeError(f"PS failed: {result.stderr}")

    raw = result.stdout.strip()
    if not raw:
        return []

    data = json.loads(raw)
    if isinstance(data, dict):
        data = [data]

    return [_normalize(d) for d in data]


def _scan_via_diskpart() -> List[dict]:
    """
    Fallback: use diskpart to list volumes.
    Less detailed but works in minimal WinPE environments.
    """
    script = "list volume\r\nexit\r\n"
    result = subprocess.run(
        ["diskpart"], input=script, capture_output=True, text=True, timeout=20
    )

    partitions = []
    lines = result.stdout.splitlines()
    for line in lines:
        if "Volume" not in line:
            continue
        parts = line.split()
        try:
            # Typical diskpart output:
            # Volume ###  Ltr  Label      Fs     Type        Size     Status     Info
            # Volume 0     C   System     NTFS   Partition    100 GB  Healthy    Boot
            vol_idx = int(parts[1])
            if len(parts) < 4:
                continue
            letter = parts[2] if len(parts[2]) == 1 else ""
            if not letter.isalpha():
                letter = ""
            label  = parts[3] if len(parts) > 3 else ""
            fs     = parts[4] if len(parts) > 4 else "Unknown"
            partitions.append({
                "letter":          letter,
                "label":           label,
                "fs":              fs,
                "size_bytes":      0,
                "used_bytes":      0,
                "device_path":     f"\\\\.\\{letter}:" if letter else "",
                "partition_index": vol_idx,
                "disk_index":      0,
                "offset_bytes":    0,
                "is_system":       letter == "C",
                "is_active":       False,
            })
        except (IndexError, ValueError):
            continue

    return partitions


def _normalize(d: dict) -> dict:
    return {
        "letter":          str(d.get("letter", "?")),
        "label":           str(d.get("label", "")),
        "fs":              str(d.get("fs", "Unknown")),
        "size_bytes":      int(d.get("size_bytes", 0) or 0),
        "used_bytes":      int(d.get("used_bytes", 0) or 0),
        "device_path":     str(d.get("device_path", "")),
        "partition_index": int(d.get("partition_index", 0) or 0),
        "disk_index":      int(d.get("disk_index", 0) or 0),
        "offset_bytes":    int(d.get("offset_bytes", 0) or 0),
        "is_system":       bool(d.get("is_system", False)),
        "is_active":       bool(d.get("is_active", False)),
    }
