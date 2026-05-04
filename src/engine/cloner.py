"""
OmniClone Universal - Clone Engine (Source Side)
Reads used blocks from source partition, compresses with lz4,
verifies with MD5, and streams to target agent over TCP.
"""

import socket
import struct
import time
import threading
import logging
from typing import Callable, Optional

try:
    import lz4.frame as lz4
except ImportError:
    lz4 = None

from .partition_reader import PartitionReader, BLOCK_SIZE
from ..protocol.messages import (
    PartitionInfo, BlockData,
    pack_message, unpack_header, encode_json, decode_json, compute_md5,
    HEADER_SIZE,
    MSG_START_CLONE, MSG_BLOCK, MSG_BLOCK_ACK, MSG_BLOCK_ERR,
    MSG_CLONE_DONE, MSG_BOOT_REPAIR, MSG_BOOT_DONE, MSG_ERROR,
)

logger = logging.getLogger("omniclone.cloner")

RECV_TIMEOUT  = 30   # seconds to wait for ACK
MAX_RETRIES   = 5    # max block retries on checksum error
AGENT_PORT    = 9876


class CloneProgress:
    """Tracks and reports clone progress."""

    def __init__(self, total_bytes: int,
                 on_progress: Optional[Callable[[int, int, float, float], None]] = None):
        self.total_bytes   = total_bytes
        self.sent_bytes    = 0
        self.blocks_sent   = 0
        self.start_time    = time.monotonic()
        self.on_progress   = on_progress  # (sent, total, pct, mb_per_sec)

    def update(self, bytes_sent: int):
        self.sent_bytes  += bytes_sent
        self.blocks_sent += 1
        elapsed = time.monotonic() - self.start_time
        speed = (self.sent_bytes / (1024 * 1024)) / elapsed if elapsed > 0 else 0
        pct   = (self.sent_bytes / self.total_bytes * 100) if self.total_bytes > 0 else 0
        if self.on_progress:
            self.on_progress(self.sent_bytes, self.total_bytes, pct, speed)

    def eta_seconds(self) -> float:
        elapsed = time.monotonic() - self.start_time
        if self.sent_bytes == 0:
            return 0
        rate = self.sent_bytes / elapsed
        remaining = self.total_bytes - self.sent_bytes
        return remaining / rate if rate > 0 else 0


class ClonerEngine:
    """
    Manages the full clone operation from source machine to target agent.
    Runs in a background thread; reports progress via callbacks.
    """

    def __init__(self,
                 source_partition: PartitionInfo,
                 target_ip: str,
                 on_progress: Optional[Callable[[int, int, float, float], None]] = None,
                 on_status: Optional[Callable[[str], None]] = None,
                 on_done: Optional[Callable[[bool, str], None]] = None):
        self.source_partition = source_partition
        self.target_ip        = target_ip
        self.on_progress      = on_progress
        self.on_status        = on_status
        self.on_done          = on_done
        self._stop_event      = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._sock: Optional[socket.socket] = None

    def _status(self, msg: str):
        logger.info(msg)
        if self.on_status:
            self.on_status(msg)

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass

    def _connect(self) -> socket.socket:
        self._status(f"الاتصال بالهدف {self.target_ip}:{AGENT_PORT} ...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(15)
        sock.connect((self.target_ip, AGENT_PORT))
        sock.settimeout(RECV_TIMEOUT)
        self._sock = sock
        self._status("تم الاتصال بنجاح.")
        return sock

    def _send_msg(self, sock: socket.socket, msg_type: int, payload: bytes):
        data = pack_message(msg_type, payload)
        sock.sendall(data)

    def _recv_msg(self, sock: socket.socket):
        header = self._recv_exact(sock, HEADER_SIZE)
        msg_type, flags, payload_len = unpack_header(header)
        payload = self._recv_exact(sock, payload_len) if payload_len > 0 else b""
        return msg_type, flags, payload

    def _recv_exact(self, sock: socket.socket, n: int) -> bytes:
        buf = bytearray()
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("Connection closed by target agent.")
            buf.extend(chunk)
        return bytes(buf)

    def _compress(self, data: bytes) -> bytes:
        if lz4 is None:
            return data  # fallback: no compression
        return lz4.compress(data, compression_level=1)

    def _run(self):
        try:
            sock = self._connect()
            with PartitionReader(self.source_partition) as reader:
                total_bytes = reader.used_bytes()
                progress    = CloneProgress(total_bytes, self.on_progress)

                # Tell agent to prepare for cloning
                self._send_msg(sock, MSG_START_CLONE, encode_json({
                    "total_used_bytes": total_bytes,
                    "block_size": BLOCK_SIZE,
                    "compression": "lz4" if lz4 else "none",
                }))
                msg_type, _, _ = self._recv_msg(sock)
                if msg_type == MSG_ERROR:
                    raise RuntimeError("Target agent rejected start signal.")

                self._status("بدء نقل البيانات...")
                block_index = 0

                for offset, raw_data in reader.iter_blocks(BLOCK_SIZE):
                    if self._stop_event.is_set():
                        self._status("تم إيقاف العملية من قبل المستخدم.")
                        return

                    md5_hash    = compute_md5(raw_data)
                    compressed  = self._compress(raw_data)

                    block_meta = {
                        "block_index":     block_index,
                        "offset":          offset,
                        "original_size":   len(raw_data),
                        "compressed_size": len(compressed),
                        "md5":             md5_hash,
                        "is_last":         False,
                    }
                    meta_bytes  = encode_json(block_meta)
                    meta_len    = struct.pack("!I", len(meta_bytes))
                    payload     = meta_len + meta_bytes + compressed

                    retries = 0
                    while retries < MAX_RETRIES:
                        self._send_msg(sock, MSG_BLOCK, payload)
                        ack_type, _, ack_payload = self._recv_msg(sock)

                        if ack_type == MSG_BLOCK_ACK:
                            break
                        elif ack_type == MSG_BLOCK_ERR:
                            retries += 1
                            self._status(f"خطأ في التحقق من البلوك {block_index}، إعادة الإرسال ({retries}/{MAX_RETRIES})")
                        elif ack_type == MSG_ERROR:
                            raise RuntimeError(f"Target error on block {block_index}: {ack_payload.decode()}")
                        else:
                            retries += 1

                    if retries >= MAX_RETRIES:
                        raise RuntimeError(f"فشل إرسال البلوك {block_index} بعد {MAX_RETRIES} محاولات.")

                    progress.update(len(raw_data))
                    block_index += 1

                # Signal end of transfer
                self._send_msg(sock, MSG_CLONE_DONE, encode_json({
                    "total_blocks": block_index,
                    "total_bytes":  total_bytes,
                }))

                self._status("اكتمل نقل البيانات. بدء إصلاح بيانات الإقلاع...")

                # Request boot repair
                self._send_msg(sock, MSG_BOOT_REPAIR, encode_json({
                    "firmware": "auto",
                }))
                msg_type, _, payload = self._recv_msg(sock)
                if msg_type == MSG_BOOT_DONE:
                    result = decode_json(payload)
                    if result.get("success"):
                        self._status(f"إصلاح الإقلاع نجح: {result.get('message','')}")
                    else:
                        self._status(f"تحذير - إصلاح الإقلاع: {result.get('message','')}")

            sock.close()
            if self.on_done:
                self.on_done(True, "اكتملت عملية النسخ بنجاح!")

        except Exception as e:
            logger.exception("Clone failed")
            if self.on_done:
                self.on_done(False, f"فشلت عملية النسخ: {e}")
