"""
OmniClone Universal - Communication Protocol
Defines all message types between source GUI and target agent.
"""

import json
import struct
import hashlib
from dataclasses import dataclass, asdict
from typing import List, Optional

# Protocol constants
MAGIC = b"OMNI"
VERSION = 1
HEADER_SIZE = 16  # magic(4) + version(1) + msg_type(1) + flags(2) + payload_len(8)

# Message types
MSG_HELLO          = 0x01  # Agent -> Source: announce presence
MSG_PARTITION_LIST = 0x02  # Agent -> Source: send partition table
MSG_SELECT_TARGET  = 0x03  # Source -> Agent: select target partition + lock others
MSG_SELECT_ACK     = 0x04  # Agent -> Source: confirmation + lock status
MSG_START_CLONE    = 0x05  # Source -> Agent: begin receiving blocks
MSG_BLOCK          = 0x06  # Source -> Agent: compressed data block
MSG_BLOCK_ACK      = 0x07  # Agent -> Source: block received + checksum OK
MSG_BLOCK_ERR      = 0x08  # Agent -> Source: checksum mismatch, resend
MSG_CLONE_DONE     = 0x09  # Source -> Agent: all blocks sent
MSG_BOOT_REPAIR    = 0x0A  # Source -> Agent: trigger bcdboot
MSG_BOOT_DONE      = 0x0B  # Agent -> Source: boot repair result
MSG_ERROR          = 0xFF  # Either direction: fatal error


@dataclass
class PartitionInfo:
    letter: str          # Drive letter, e.g. "C"
    label: str           # Volume label
    fs: str              # File system: NTFS, FAT32, etc.
    size_bytes: int      # Total size
    used_bytes: int      # Used space
    device_path: str     # Physical device path, e.g. \\.\PhysicalDrive0
    partition_index: int # Partition index on disk
    disk_index: int      # Disk number
    offset_bytes: int    # Partition start offset on disk
    is_system: bool      # True if this is the system/boot partition
    is_active: bool      # True if partition is marked active

    def to_dict(self):
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "PartitionInfo":
        return PartitionInfo(**d)


@dataclass
class BlockData:
    block_index: int     # Sequential block number
    offset: int          # Byte offset from partition start
    original_size: int   # Uncompressed size
    compressed_size: int # Compressed payload size
    md5: str             # MD5 of the ORIGINAL (uncompressed) data
    is_last: bool        # True if this is the final block
    payload: bytes       # lz4-compressed block data

    def header_dict(self):
        return {
            "block_index": self.block_index,
            "offset": self.offset,
            "original_size": self.original_size,
            "compressed_size": self.compressed_size,
            "md5": self.md5,
            "is_last": self.is_last,
        }


def pack_message(msg_type: int, payload: bytes, flags: int = 0) -> bytes:
    """Pack a message with header for sending over TCP."""
    header = struct.pack(
        "!4sBBHQ",
        MAGIC,
        VERSION,
        msg_type,
        flags,
        len(payload)
    )
    return header + payload


def unpack_header(data: bytes):
    """Unpack message header. Returns (msg_type, flags, payload_len) or raises."""
    if len(data) < HEADER_SIZE:
        raise ValueError(f"Header too short: {len(data)} bytes")
    magic, version, msg_type, flags, payload_len = struct.unpack("!4sBBHQ", data[:HEADER_SIZE])
    if magic != MAGIC:
        raise ValueError(f"Invalid magic bytes: {magic}")
    if version != VERSION:
        raise ValueError(f"Unknown protocol version: {version}")
    return msg_type, flags, payload_len


def encode_json(obj) -> bytes:
    if hasattr(obj, "to_dict"):
        obj = obj.to_dict()
    elif hasattr(obj, "__dict__"):
        obj = obj.__dict__
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def decode_json(data: bytes) -> dict:
    return json.loads(data.decode("utf-8"))


def compute_md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()
