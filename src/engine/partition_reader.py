"""
OmniClone Universal - Partition Reader (Source Side)
Opens the selected partition in READ-ONLY mode and streams used sectors.
Windows only — uses ctypes + win32 APIs.
"""

import ctypes
import ctypes.wintypes
import struct
import os
import subprocess
import json
from typing import Iterator, Tuple, List
from ..protocol.messages import PartitionInfo, compute_md5

# Windows constants
GENERIC_READ         = 0x80000000
FILE_SHARE_READ      = 0x00000001
FILE_SHARE_WRITE     = 0x00000002
OPEN_EXISTING        = 3
FILE_FLAG_NO_BUFFERING      = 0x20000000
FILE_FLAG_SEQUENTIAL_SCAN   = 0x08000000
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS  = 0x00560000
IOCTL_DISK_GET_PARTITION_INFO_EX       = 0x00070048
FSCTL_GET_NTFS_VOLUME_DATA             = 0x00090064
FSCTL_GET_RETRIEVAL_POINTERS           = 0x00090073
FSCTL_GET_BITMAP                       = 0x0009006F

BLOCK_SIZE = 4 * 1024 * 1024  # 4 MB read chunks


class WindowsError(Exception):
    pass


def _open_volume_readonly(path: str):
    """Open a volume or physical device in READ-ONLY mode."""
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateFileW(
        path,
        GENERIC_READ,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        None,
        OPEN_EXISTING,
        FILE_FLAG_NO_BUFFERING | FILE_FLAG_SEQUENTIAL_SCAN,
        None
    )
    if handle == INVALID_HANDLE_VALUE:
        err = ctypes.get_last_error()
        raise WindowsError(f"Cannot open {path}: error {err}")
    return handle


def _close_handle(handle):
    ctypes.windll.kernel32.CloseHandle(handle)


def _device_io_control(handle, code, in_buf=None, out_size=4096):
    kernel32 = ctypes.windll.kernel32
    out_buf = ctypes.create_string_buffer(out_size)
    bytes_returned = ctypes.wintypes.DWORD(0)
    in_ptr = ctypes.cast(in_buf, ctypes.c_char_p) if in_buf else None
    in_size = len(in_buf) if in_buf else 0
    ret = kernel32.DeviceIoControl(
        handle, code,
        in_ptr, in_size,
        out_buf, out_size,
        ctypes.byref(bytes_returned),
        None
    )
    if not ret:
        err = ctypes.get_last_error()
        raise WindowsError(f"DeviceIoControl 0x{code:08X} failed: error {err}")
    return out_buf.raw[:bytes_returned.value]


def _seek(handle, offset: int):
    kernel32 = ctypes.windll.kernel32
    offset_high = ctypes.wintypes.LONG(offset >> 32)
    offset_low  = ctypes.wintypes.LONG(offset & 0xFFFFFFFF)
    result = kernel32.SetFilePointer(handle, offset_low, ctypes.byref(offset_high), 0)
    if result == 0xFFFFFFFF:
        err = ctypes.get_last_error()
        if err != 0:
            raise WindowsError(f"Seek to {offset} failed: error {err}")


def _read_raw(handle, size: int) -> bytes:
    kernel32 = ctypes.windll.kernel32
    buf = ctypes.create_string_buffer(size)
    bytes_read = ctypes.wintypes.DWORD(0)
    ret = kernel32.ReadFile(handle, buf, size, ctypes.byref(bytes_read), None)
    if not ret:
        err = ctypes.get_last_error()
        raise WindowsError(f"ReadFile failed: error {err}")
    return buf.raw[:bytes_read.value]


class NTFSBitmap:
    """
    Fetches the NTFS cluster allocation bitmap via FSCTL_GET_BITMAP.
    Used to skip empty (unallocated) clusters for smart block-level transfer.
    """

    def __init__(self, volume_handle, cluster_size: int, total_clusters: int):
        self.cluster_size = cluster_size
        self.total_clusters = total_clusters
        self.bitmap_data = self._fetch_bitmap(volume_handle)

    def _fetch_bitmap(self, handle) -> bytes:
        # STARTING_LCN_INPUT_BUFFER: LARGE_INTEGER = 0
        in_buf = struct.pack("<q", 0)
        chunk_size = 65536 + 8
        all_bits = bytearray()
        starting_lcn = 0

        while True:
            in_buf = struct.pack("<q", starting_lcn)
            try:
                raw = _device_io_control(handle, FSCTL_GET_BITMAP, in_buf, 1024 * 1024)
            except WindowsError:
                break
            # VOLUME_BITMAP_BUFFER: StartingLcn(8) + BitmapSize(8) + Buffer(...)
            _start, bitmap_size = struct.unpack_from("<qq", raw, 0)
            bitmap_bytes = raw[16:]
            all_bits.extend(bitmap_bytes)
            if len(all_bits) * 8 >= self.total_clusters:
                break
            starting_lcn += len(bitmap_bytes) * 8

        return bytes(all_bits)

    def is_allocated(self, cluster_index: int) -> bool:
        byte_idx = cluster_index // 8
        bit_idx  = cluster_index % 8
        if byte_idx >= len(self.bitmap_data):
            return False
        return bool(self.bitmap_data[byte_idx] & (1 << bit_idx))

    def allocated_ranges(self) -> Iterator[Tuple[int, int]]:
        """Yield (start_cluster, end_cluster) inclusive ranges of allocated clusters."""
        i = 0
        n = self.total_clusters
        while i < n:
            if self.is_allocated(i):
                start = i
                while i < n and self.is_allocated(i):
                    i += 1
                yield start, i - 1
            else:
                i += 1


class PartitionReader:
    """
    Opens a partition in READ-ONLY mode and iterates used sectors.
    Uses the NTFS bitmap to skip free space for maximum efficiency.
    """

    def __init__(self, partition: PartitionInfo):
        self.partition = partition
        self._vol_handle = None
        self._disk_handle = None
        self.cluster_size = 0
        self.total_clusters = 0
        self.bytes_per_sector = 512

    def open(self):
        vol_path = f"\\\\.\\{self.partition.letter}:"
        self._vol_handle = _open_volume_readonly(vol_path)

        raw = _device_io_control(self._vol_handle, FSCTL_GET_NTFS_VOLUME_DATA, out_size=512)
        # NTFS_VOLUME_DATA_BUFFER layout (partial):
        # VolumeSerialNumber(8), NumberSectors(8), TotalClusters(8), FreeClusters(8),
        # TotalReserved(8), BytesPerSector(4), BytesPerCluster(4), ...
        (_, _, total_clusters, _, _, bytes_per_sector, bytes_per_cluster) = struct.unpack_from("<qqqqqII", raw, 0)
        self.cluster_size    = bytes_per_cluster
        self.total_clusters  = total_clusters
        self.bytes_per_sector = bytes_per_sector

        disk_path = f"\\\\.\\PhysicalDrive{self.partition.disk_index}"
        self._disk_handle = _open_volume_readonly(disk_path)

    def close(self):
        if self._vol_handle:
            _close_handle(self._vol_handle)
            self._vol_handle = None
        if self._disk_handle:
            _close_handle(self._disk_handle)
            self._disk_handle = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *_):
        self.close()

    def used_bytes(self) -> int:
        return self.partition.used_bytes

    def iter_blocks(self, block_size: int = BLOCK_SIZE) -> Iterator[Tuple[int, bytes]]:
        """
        Yields (offset_from_partition_start, raw_data) for every USED block.
        Skips empty clusters. Reads from the physical disk using absolute offsets.
        """
        bitmap = NTFSBitmap(self._vol_handle, self.cluster_size, self.total_clusters)
        partition_start = self.partition.offset_bytes

        for start_cluster, end_cluster in bitmap.allocated_ranges():
            cluster_offset = start_cluster * self.cluster_size
            byte_count = (end_cluster - start_cluster + 1) * self.cluster_size

            # Read in block_size chunks
            read_pos = 0
            while read_pos < byte_count:
                chunk = min(block_size, byte_count - read_pos)
                # Align to sector boundary (required for NO_BUFFERING)
                aligned_chunk = ((chunk + self.bytes_per_sector - 1)
                                 // self.bytes_per_sector * self.bytes_per_sector)

                abs_offset = partition_start + cluster_offset + read_pos
                _seek(self._disk_handle, abs_offset)
                data = _read_raw(self._disk_handle, aligned_chunk)
                data = data[:chunk]  # trim to actual requested size

                yield cluster_offset + read_pos, data
                read_pos += len(data)


def list_local_partitions() -> List[PartitionInfo]:
    """
    Enumerate all accessible partitions on the source machine using WMI via PowerShell.
    Returns a list of PartitionInfo objects.
    """
    ps_script = r"""
$partitions = Get-WmiObject Win32_DiskPartition
$volumes    = Get-WmiObject Win32_Volume | Where-Object { $_.DriveLetter -ne $null }
$result     = @()

foreach ($vol in $volumes) {
    $letter = $vol.DriveLetter.TrimEnd(':').TrimEnd('\\')
    if ($letter -eq '') { continue }

    $diskQuery = "ASSOCIATORS OF {Win32_Volume.DeviceID='$($vol.DeviceID -replace '\\\\','\\\\')' } WHERE AssocClass=Win32_DiskDriveToDiskPartition"

    $size      = [long]$vol.Capacity
    $free      = [long]$vol.FreeSpace
    $used      = $size - $free
    $fs        = $vol.FileSystem
    $label     = $vol.Label

    $isSystem  = ($vol.SystemVolume -eq $true) -or ($letter -eq 'C')

    $diskIndex = 0
    $partIndex = 0
    $offset    = 0

    foreach ($part in $partitions) {
        $assocVols = Get-WmiObject -Query "ASSOCIATORS OF {Win32_DiskPartition.DeviceID='$($part.DeviceID)'} WHERE AssocClass=Win32_LogicalDiskToPartition"
        foreach ($av in $assocVols) {
            if ($av.DeviceID -eq ($letter + ':')) {
                $diskIndex = $part.DiskIndex
                $partIndex = $part.Index
                $offset    = [long]$part.StartingOffset
            }
        }
    }

    $obj = [PSCustomObject]@{
        letter          = $letter
        label           = if ($label) { $label } else { '' }
        fs              = if ($fs) { $fs } else { 'Unknown' }
        size_bytes      = $size
        used_bytes      = $used
        device_path     = "\\\\.\\" + $letter + ":"
        partition_index = $partIndex
        disk_index      = $diskIndex
        offset_bytes    = $offset
        is_system       = $isSystem
        is_active       = $false
    }
    $result += $obj
}

$result | ConvertTo-Json -Depth 3
"""
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive",
         "-ExecutionPolicy", "Bypass", "-Command", ps_script],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        raise RuntimeError(f"PowerShell partition query failed: {result.stderr}")

    raw = result.stdout.strip()
    if not raw:
        return []

    data = json.loads(raw)
    if isinstance(data, dict):
        data = [data]

    partitions = []
    for d in data:
        partitions.append(PartitionInfo(
            letter          = d.get("letter", "?"),
            label           = d.get("label", ""),
            fs              = d.get("fs", "Unknown"),
            size_bytes      = int(d.get("size_bytes", 0)),
            used_bytes      = int(d.get("used_bytes", 0)),
            device_path     = d.get("device_path", ""),
            partition_index = int(d.get("partition_index", 0)),
            disk_index      = int(d.get("disk_index", 0)),
            offset_bytes    = int(d.get("offset_bytes", 0)),
            is_system       = bool(d.get("is_system", False)),
            is_active       = bool(d.get("is_active", False)),
        ))
    return partitions
