"""
OmniClone Agent - Main Entry Point (Target Side / WinPE)
This program runs on the target PC after booting from PXE.
It:
  1. Scans local partitions and reports them to the source GUI
  2. Waits for the user to select the target partition
  3. Locks all other partitions (Safety Lock)
  4. Receives compressed blocks from source and writes them
  5. Runs boot repair (bcdboot) after transfer completes
"""

import sys
import os
import socket
import struct
import logging
import threading
import time
import ctypes

# Add parent dir to path so we can import shared protocol
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from src.protocol.messages import (
    PartitionInfo, pack_message, unpack_header, encode_json, decode_json,
    HEADER_SIZE,
    MSG_HELLO, MSG_PARTITION_LIST, MSG_SELECT_TARGET, MSG_SELECT_ACK,
    MSG_START_CLONE, MSG_BLOCK, MSG_BLOCK_ACK, MSG_BLOCK_ERR,
    MSG_CLONE_DONE, MSG_BOOT_REPAIR, MSG_BOOT_DONE, MSG_ERROR,
)
from partition_scanner import scan_partitions
from partition_writer import PartitionWriter
from lock_manager import lock_all_except
from src.engine.boot_repair import run_boot_repair

# Agent configuration
SOURCE_IP   = "192.168.100.1"
AGENT_PORT  = 9876
LOG_FILE    = "C:\\OmniClone_Agent.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger("agent")


def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def wait_for_network(timeout: int = 60) -> bool:
    """Wait for the network to come up after PXE boot."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            s = socket.create_connection((SOURCE_IP, AGENT_PORT), timeout=2)
            s.close()
            return True
        except OSError:
            time.sleep(2)
    return False


def recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Connection closed by source")
        buf.extend(chunk)
    return bytes(buf)


def run_agent():
    if not is_admin():
        logger.error("Agent must run as Administrator / SYSTEM. Exiting.")
        sys.exit(1)

    logger.info("=== OmniClone Agent Starting ===")

    # Step 1: Scan partitions
    logger.info("Scanning local partitions...")
    raw_partitions = scan_partitions()
    partitions = [PartitionInfo.from_dict(p) for p in raw_partitions]
    logger.info(f"Found {len(partitions)} partition(s): {[p.letter for p in partitions]}")

    # Step 2: Wait for network and connect to source
    logger.info(f"Waiting for network connectivity to {SOURCE_IP}:{AGENT_PORT}...")
    # Give network a moment to stabilize after DHCP
    time.sleep(3)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(30)

    connected = False
    for attempt in range(10):
        try:
            sock.connect((SOURCE_IP, AGENT_PORT))
            connected = True
            break
        except OSError:
            logger.info(f"Connection attempt {attempt + 1}/10 failed, retrying...")
            time.sleep(3)

    if not connected:
        logger.error("Cannot connect to source machine. Exiting.")
        sys.exit(1)

    logger.info("Connected to source machine.")

    try:
        import socket as _s
        hostname = _s.gethostname()
    except Exception:
        hostname = "WinPE-Target"

    # Step 3: Send HELLO
    hello_payload = encode_json({"hostname": hostname, "agent_version": "1.0"})
    sock.sendall(pack_message(MSG_HELLO, hello_payload))
    logger.info("Sent HELLO to source.")

    # Step 4: Send partition list
    parts_payload = encode_json([p.to_dict() for p in partitions])
    sock.sendall(pack_message(MSG_PARTITION_LIST, parts_payload))
    logger.info("Sent partition list to source.")

    # Step 5: Wait for user to select target partition
    logger.info("Waiting for source to select target partition...")
    sock.settimeout(300)  # 5 minutes for user interaction
    header = recv_exact(sock, HEADER_SIZE)
    msg_type, _, payload_len = unpack_header(header)

    if msg_type != MSG_SELECT_TARGET:
        logger.error(f"Unexpected message: {msg_type}")
        sock.sendall(pack_message(MSG_ERROR, b"Expected SELECT_TARGET"))
        sys.exit(1)

    payload = recv_exact(sock, payload_len)
    target_part_dict = decode_json(payload)
    target = PartitionInfo.from_dict(target_part_dict)
    logger.info(f"Target partition selected: {target.letter}:")

    # Step 6: Safety Lock — lock all other partitions
    all_letters = [p.letter for p in partitions]
    lock_results = lock_all_except(all_letters, target.letter)
    logger.info(f"Lock results: {lock_results}")

    locked_ok = all(v in ("locked", "target", "winpe_skip") for v in lock_results.values())
    ack_payload = encode_json({
        "success": True,
        "message": f"القسم {target.letter}: جاهز للكتابة. تم تأمين الأقسام الأخرى.",
        "lock_results": lock_results,
    })
    sock.sendall(pack_message(MSG_SELECT_ACK, ack_payload))
    logger.info("Sent SELECT_ACK to source.")

    # Step 7: Receive START_CLONE
    sock.settimeout(60)
    header = recv_exact(sock, HEADER_SIZE)
    msg_type, _, payload_len = unpack_header(header)
    if msg_type != MSG_START_CLONE:
        logger.error(f"Expected MSG_START_CLONE, got {msg_type}")
        sys.exit(1)
    start_info = decode_json(recv_exact(sock, payload_len))
    total_bytes = start_info.get("total_used_bytes", 0)
    logger.info(f"Clone starting. Total bytes to receive: {total_bytes:,}")

    # Acknowledge ready
    sock.sendall(pack_message(MSG_BLOCK_ACK, encode_json({"ready": True})))

    # Step 8: Receive and write blocks
    sock.settimeout(120)
    total_received = 0
    blocks_written = 0

    with PartitionWriter(target.letter, partition_offset=target.offset_bytes) as writer:
        while True:
            header = recv_exact(sock, HEADER_SIZE)
            msg_type, _, payload_len = unpack_header(header)
            payload = recv_exact(sock, payload_len) if payload_len else b""

            if msg_type == MSG_CLONE_DONE:
                done_info = decode_json(payload)
                logger.info(f"Clone done. Total blocks: {done_info.get('total_blocks')}")
                break

            if msg_type == MSG_ERROR:
                logger.error(f"Source error: {payload.decode(errors='replace')}")
                sys.exit(1)

            if msg_type != MSG_BLOCK:
                logger.warning(f"Unexpected message type: {msg_type}, skipping")
                continue

            # Parse block: 4 bytes meta_len + meta_json + compressed_data
            meta_len = struct.unpack("!I", payload[:4])[0]
            meta     = decode_json(payload[4:4 + meta_len])
            compressed = payload[4 + meta_len:]

            block_index   = meta["block_index"]
            offset        = meta["offset"]
            original_size = meta["original_size"]
            expected_md5  = meta["md5"]
            is_last       = meta.get("is_last", False)

            success, actual_md5 = writer.write_block(offset, compressed, original_size, expected_md5)

            if success:
                total_received += original_size
                blocks_written += 1
                pct = (total_received / total_bytes * 100) if total_bytes > 0 else 0
                logger.info(f"Block {block_index} OK | {pct:.1f}% ({total_received:,}/{total_bytes:,} bytes)")
                sock.sendall(pack_message(MSG_BLOCK_ACK, encode_json({
                    "block_index": block_index,
                    "md5": actual_md5,
                })))
            else:
                logger.error(f"Block {block_index} FAILED: {actual_md5}")
                sock.sendall(pack_message(MSG_BLOCK_ERR, encode_json({
                    "block_index": block_index,
                    "error": actual_md5,
                })))

    logger.info(f"Transfer complete. {blocks_written} blocks, {total_received:,} bytes written.")

    # Step 9: Boot repair
    sock.settimeout(60)
    header = recv_exact(sock, HEADER_SIZE)
    msg_type, _, payload_len = unpack_header(header)

    if msg_type == MSG_BOOT_REPAIR:
        repair_info = decode_json(recv_exact(sock, payload_len))
        firmware    = repair_info.get("firmware", "auto")
        logger.info(f"Running boot repair (firmware={firmware})...")
        success, msg = run_boot_repair(target.letter, firmware_override=firmware)
        logger.info(f"Boot repair result: {success} - {msg}")
        sock.sendall(pack_message(MSG_BOOT_DONE, encode_json({
            "success": success,
            "message": msg,
        })))

    sock.close()
    logger.info("=== OmniClone Agent Finished Successfully ===")
    logger.info("يمكنك الآن إعادة تشغيل الجهاز الهدف.")

    # Keep console open in WinPE
    input("\nاكتملت العملية. اضغط Enter للخروج...")


if __name__ == "__main__":
    run_agent()
