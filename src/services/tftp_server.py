"""
OmniClone Universal - Embedded TFTP Server
Serves WinPE boot files (pxelinux.0, winpe.wim, etc.) to the PXE client.
Implements RFC 1350 with RFC 2347/2348/2349 options (blksize, timeout, tsize).
"""

import socket
import struct
import os
import threading
import logging
from typing import Optional, Dict

logger = logging.getLogger("omniclone.tftp")

TFTP_PORT     = 69
DEFAULT_BLKSIZE = 512
MAX_BLKSIZE   = 65464
TIMEOUT_SEC   = 5
MAX_RETRIES   = 6

# Opcodes
OP_RRQ    = 1
OP_WRQ    = 2
OP_DATA   = 3
OP_ACK    = 4
OP_ERROR  = 5
OP_OACK   = 6

# Error codes
ERR_NOT_FOUND    = 1
ERR_ACCESS       = 2
ERR_DISK_FULL    = 3
ERR_ILLEGAL      = 4
ERR_UNKNOWN_TID  = 5
ERR_FILE_EXISTS  = 6
ERR_NO_USER      = 7


def _make_data(block: int, data: bytes) -> bytes:
    return struct.pack("!HH", OP_DATA, block) + data


def _make_ack(block: int) -> bytes:
    return struct.pack("!HH", OP_ACK, block)


def _make_error(code: int, msg: str) -> bytes:
    return struct.pack("!HH", OP_ERROR, code) + msg.encode() + b"\x00"


def _make_oack(options: dict) -> bytes:
    parts = [struct.pack("!H", OP_OACK)]
    for k, v in options.items():
        parts.append(k.encode() + b"\x00" + str(v).encode() + b"\x00")
    return b"".join(parts)


class TFTPSession(threading.Thread):
    """Handles a single TFTP file transfer in its own thread."""

    def __init__(self, root_dir: str, filename: str, client_addr,
                 server_sock: socket.socket, options: dict):
        super().__init__(daemon=True)
        self.root_dir    = root_dir
        self.filename    = filename
        self.client_addr = client_addr
        self.options     = options
        self.blksize     = int(options.get("blksize", DEFAULT_BLKSIZE))
        self.blksize     = min(self.blksize, MAX_BLKSIZE)
        self.timeout     = int(options.get("timeout", TIMEOUT_SEC))
        self._sock       = None

    def run(self):
        filepath = os.path.normpath(os.path.join(self.root_dir, self.filename.lstrip("/")))
        # Security: prevent path traversal
        if not filepath.startswith(os.path.abspath(self.root_dir)):
            logger.warning(f"Path traversal attempt: {self.filename}")
            return

        if not os.path.isfile(filepath):
            logger.warning(f"File not found: {filepath}")
            self._send_error(ERR_NOT_FOUND, f"File not found: {self.filename}")
            return

        file_size = os.path.getsize(filepath)
        logger.info(f"TFTP RRQ: {self.filename} ({file_size} bytes) -> {self.client_addr}")

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(self.timeout)
            sock.bind(("", 0))  # ephemeral port for this session
            self._sock = sock

            # Send OACK if client sent options
            if self.options:
                ack_opts = {}
                if "blksize" in self.options:
                    ack_opts["blksize"] = self.blksize
                if "timeout" in self.options:
                    ack_opts["timeout"] = self.timeout
                if "tsize" in self.options:
                    ack_opts["tsize"] = file_size
                sock.sendto(_make_oack(ack_opts), self.client_addr)
                # Wait for ACK 0
                try:
                    data, addr = sock.recvfrom(16)
                    op, block = struct.unpack("!HH", data[:4])
                    if op != OP_ACK or block != 0:
                        return
                except socket.timeout:
                    return

            with open(filepath, "rb") as f:
                block_num = 1
                while True:
                    chunk = f.read(self.blksize)
                    pkt = _make_data(block_num, chunk)

                    sent = False
                    for attempt in range(MAX_RETRIES):
                        sock.sendto(pkt, self.client_addr)
                        try:
                            ack_data, addr = sock.recvfrom(64)
                            op, ack_block = struct.unpack("!HH", ack_data[:4])
                            if op == OP_ACK and ack_block == block_num:
                                sent = True
                                break
                        except socket.timeout:
                            logger.debug(f"Timeout on block {block_num}, retry {attempt + 1}")

                    if not sent:
                        logger.error(f"TFTP transfer failed at block {block_num}")
                        return

                    if len(chunk) < self.blksize:
                        # Last block
                        logger.info(f"TFTP transfer complete: {self.filename}")
                        break

                    block_num = (block_num + 1) % 65536  # wrap at 16 bits

        except Exception as e:
            logger.error(f"TFTP session error: {e}")
        finally:
            if self._sock:
                self._sock.close()

    def _send_error(self, code: int, msg: str):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.sendto(_make_error(code, msg), self.client_addr)
        except Exception:
            pass


class TFTPServer:
    """
    Embedded TFTP server. Serves files from a specified root directory.
    Each client request is handled in a dedicated thread.
    """

    def __init__(self, root_dir: str, bind_ip: str = "0.0.0.0", port: int = TFTP_PORT):
        self.root_dir = os.path.abspath(root_dir)
        self.bind_ip  = bind_ip
        self.port     = port
        self._stop    = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._sock: Optional[socket.socket] = None

    def start(self):
        os.makedirs(self.root_dir, exist_ok=True)
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="TFTPServer")
        self._thread.start()
        logger.info(f"TFTP server started. Root: {self.root_dir}, Port: {self.port}")

    def stop(self):
        self._stop.set()
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass

    def _run(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.settimeout(1.0)
            sock.bind((self.bind_ip, self.port))
            self._sock = sock
            logger.info(f"TFTP listening on {self.bind_ip}:{self.port}")

            while not self._stop.is_set():
                try:
                    data, addr = sock.recvfrom(1024)
                    self._dispatch(data, addr)
                except socket.timeout:
                    continue
                except OSError:
                    break
        except Exception as e:
            logger.error(f"TFTP server error: {e}")

    def _dispatch(self, data: bytes, addr):
        if len(data) < 4:
            return
        opcode = struct.unpack("!H", data[:2])[0]

        if opcode != OP_RRQ:
            # We only support read requests (serving PXE boot files)
            return

        # Parse filename and mode
        parts = data[2:].split(b"\x00")
        if len(parts) < 2:
            return
        filename = parts[0].decode("ascii", errors="replace")
        mode     = parts[1].decode("ascii", errors="replace").lower()

        # Parse options (blksize, timeout, tsize)
        options = {}
        i = 2
        while i + 1 < len(parts) and parts[i]:
            key = parts[i].decode("ascii", errors="replace").lower()
            val = parts[i + 1].decode("ascii", errors="replace")
            if key:
                options[key] = val
            i += 2

        session = TFTPSession(self.root_dir, filename, addr, self._sock, options)
        session.start()
