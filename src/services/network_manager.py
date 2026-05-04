"""
OmniClone Universal - Network Manager
Coordinates DHCP, TFTP, and agent connection listener.
Also configures the source NIC with a static IP for direct connection.
"""

import socket
import threading
import logging
import subprocess
import os
import json
from typing import Optional, Callable, List

from ..protocol.messages import (
    PartitionInfo, pack_message, unpack_header, encode_json, decode_json,
    HEADER_SIZE,
    MSG_HELLO, MSG_PARTITION_LIST, MSG_SELECT_TARGET, MSG_SELECT_ACK,
    MSG_ERROR,
)
from .dhcp_server import DHCPServer
from .tftp_server import TFTPServer

logger = logging.getLogger("omniclone.network")

AGENT_LISTEN_PORT = 9876
SOURCE_IP         = "192.168.100.1"
CLIENT_IP         = "192.168.100.2"
SUBNET_MASK       = "255.255.255.0"


class NetworkManager:
    """
    Manages all network services:
    - Configures source NIC with static IP
    - Runs DHCP server for PXE boot
    - Runs TFTP server to serve WinPE boot files
    - Listens for the target agent to connect and reports its partition list
    """

    def __init__(self,
                 tftp_root: str,
                 nic_name: Optional[str] = None,
                 on_target_connected: Optional[Callable[[str, List[PartitionInfo]], None]] = None,
                 on_status: Optional[Callable[[str], None]] = None):
        self.tftp_root           = tftp_root
        self.nic_name            = nic_name  # Windows NIC display name; None = auto-detect
        self.on_target_connected = on_target_connected
        self.on_status           = on_status

        self._dhcp  = DHCPServer(source_ip=SOURCE_IP, client_ip=CLIENT_IP)
        self._tftp  = TFTPServer(root_dir=tftp_root)
        self._stop  = threading.Event()
        self._listener_thread: Optional[threading.Thread] = None
        self._client_sock: Optional[socket.socket] = None
        self._server_sock: Optional[socket.socket] = None

    def _status(self, msg: str):
        logger.info(msg)
        if self.on_status:
            self.on_status(msg)

    def configure_static_ip(self):
        """
        Configure the first non-loopback NIC with the static source IP
        using netsh. Only needed for direct cable connections.
        """
        nic = self.nic_name or self._detect_direct_nic()
        if not nic:
            self._status("لم يتم العثور على بطاقة شبكة مناسبة للاتصال المباشر.")
            return

        self._status(f"تهيئة بطاقة الشبكة '{nic}' بعنوان IP ثابت {SOURCE_IP} ...")
        try:
            subprocess.run([
                "netsh", "interface", "ip", "set", "address",
                f"name={nic}", "source=static",
                f"addr={SOURCE_IP}", f"mask={SUBNET_MASK}", "gateway=none"
            ], check=True, capture_output=True, timeout=15)
            self._status(f"تم تعيين IP {SOURCE_IP} على '{nic}' بنجاح.")
        except subprocess.CalledProcessError as e:
            self._status(f"فشل تعيين IP: {e.stderr.decode(errors='replace')}")

    def _detect_direct_nic(self) -> Optional[str]:
        """Find the Ethernet NIC most likely connected directly (no internet)."""
        try:
            result = subprocess.run(
                ["powershell", "-Command",
                 "Get-NetAdapter | Where-Object {$_.Status -eq 'Up' -and $_.InterfaceDescription -notlike '*Wi-Fi*' -and $_.InterfaceDescription -notlike '*Wireless*'} | Select-Object -First 1 -ExpandProperty Name"],
                capture_output=True, text=True, timeout=10
            )
            name = result.stdout.strip()
            return name if name else None
        except Exception:
            return None

    def start_services(self):
        self.configure_static_ip()
        self._dhcp.start()
        self._tftp.start()
        self._status("خدمات DHCP و TFTP تعمل. في انتظار الإقلاع عبر PXE...")

        self._stop.clear()
        self._listener_thread = threading.Thread(
            target=self._listen_for_agent, daemon=True, name="AgentListener"
        )
        self._listener_thread.start()

    def stop_services(self):
        self._stop.set()
        self._dhcp.stop()
        self._tftp.stop()
        if self._client_sock:
            try:
                self._client_sock.close()
            except Exception:
                pass
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass

    def _listen_for_agent(self):
        """Wait for the target agent to connect and announce itself."""
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.settimeout(1.0)
            srv.bind(("0.0.0.0", AGENT_LISTEN_PORT))
            srv.listen(1)
            self._server_sock = srv
            self._status(f"في انتظار اتصال الجهاز الهدف على المنفذ {AGENT_LISTEN_PORT}...")

            while not self._stop.is_set():
                try:
                    conn, addr = srv.accept()
                    self._status(f"تم الاتصال من {addr[0]}")
                    self._client_sock = conn
                    self._handle_agent_hello(conn, addr[0])
                    break
                except socket.timeout:
                    continue
                except OSError:
                    break
        except Exception as e:
            logger.error(f"Agent listener error: {e}")

    def _recv_exact(self, sock: socket.socket, n: int) -> bytes:
        buf = bytearray()
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("Connection closed")
            buf.extend(chunk)
        return bytes(buf)

    def _handle_agent_hello(self, conn: socket.socket, client_ip: str):
        """Receive HELLO and PARTITION_LIST from the target agent."""
        try:
            conn.settimeout(30)
            # Receive HELLO
            header = self._recv_exact(conn, HEADER_SIZE)
            msg_type, flags, payload_len = unpack_header(header)
            if msg_type != MSG_HELLO:
                raise ValueError(f"Expected MSG_HELLO, got {msg_type}")
            payload = self._recv_exact(conn, payload_len) if payload_len else b""
            hello = decode_json(payload) if payload else {}
            self._status(f"مرحباً بالجهاز الهدف: {hello.get('hostname','مجهول')}")

            # Receive PARTITION_LIST
            header = self._recv_exact(conn, HEADER_SIZE)
            msg_type, flags, payload_len = unpack_header(header)
            if msg_type != MSG_PARTITION_LIST:
                raise ValueError(f"Expected MSG_PARTITION_LIST, got {msg_type}")
            payload = self._recv_exact(conn, payload_len)
            part_list_raw = decode_json(payload)
            partitions = [PartitionInfo.from_dict(p) for p in part_list_raw]

            self._status(f"تم استلام {len(partitions)} قسم من الجهاز الهدف.")

            if self.on_target_connected:
                self.on_target_connected(client_ip, partitions)

        except Exception as e:
            logger.error(f"Agent handshake failed: {e}")
            try:
                err_pkt = pack_message(MSG_ERROR, str(e).encode())
                conn.sendall(err_pkt)
            except Exception:
                pass

    def send_target_selection(self, selected_partition: PartitionInfo):
        """Tell the target agent which partition to write to (and lock others)."""
        if not self._client_sock:
            raise RuntimeError("No target connected")
        payload = encode_json(selected_partition.to_dict())
        pkt = pack_message(MSG_SELECT_TARGET, payload)
        self._client_sock.sendall(pkt)

        # Wait for ACK
        header = self._recv_exact(self._client_sock, HEADER_SIZE)
        msg_type, _, payload_len = unpack_header(header)
        payload = self._recv_exact(self._client_sock, payload_len) if payload_len else b""
        if msg_type == MSG_SELECT_ACK:
            result = decode_json(payload)
            return result.get("success", False), result.get("message", "")
        elif msg_type == MSG_ERROR:
            return False, payload.decode(errors="replace")
        return False, "استجابة غير متوقعة"

    def get_client_socket(self) -> Optional[socket.socket]:
        return self._client_sock
