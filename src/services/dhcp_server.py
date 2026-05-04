"""
OmniClone Universal - Embedded DHCP Server
Assigns static IPs for direct Ethernet connection between source and target.
Implements a minimal DHCP server sufficient for PXE boot.
"""

import socket
import struct
import threading
import logging
import time
from typing import Optional

logger = logging.getLogger("omniclone.dhcp")

# DHCP constants
DHCP_SERVER_PORT = 67
DHCP_CLIENT_PORT = 68
BROADCAST_IP     = "255.255.255.255"

# Message types
DHCPDISCOVER = 1
DHCPOFFER    = 2
DHCPREQUEST  = 3
DHCPACK      = 5
DHCPNAK      = 6

# Option codes
OPT_SUBNET_MASK      = 1
OPT_ROUTER           = 3
OPT_DNS              = 6
OPT_HOSTNAME         = 12
OPT_REQUESTED_IP     = 50
OPT_LEASE_TIME       = 51
OPT_MSG_TYPE         = 53
OPT_SERVER_ID        = 54
OPT_PARAM_LIST       = 55
OPT_TFTP_SERVER      = 66
OPT_BOOTFILE         = 67
OPT_CLIENT_ID        = 61
OPT_END              = 255

MAGIC_COOKIE = b"\x63\x82\x53\x63"


def _pack_option(code: int, data: bytes) -> bytes:
    return bytes([code, len(data)]) + data


def _ip_to_bytes(ip: str) -> bytes:
    return socket.inet_aton(ip)


def _mac_to_str(mac_bytes: bytes) -> str:
    return ":".join(f"{b:02x}" for b in mac_bytes[:6])


def _parse_options(data: bytes) -> dict:
    options = {}
    i = 0
    while i < len(data):
        code = data[i]
        if code == OPT_END:
            break
        if code == 0:
            i += 1
            continue
        i += 1
        if i >= len(data):
            break
        length = data[i]
        i += 1
        value = data[i:i + length]
        options[code] = value
        i += length
    return options


class DHCPServer:
    """
    Minimal DHCP server for direct cable connection.
    Assigns a fixed IP to the PXE client based on its MAC address.

    Source machine: SOURCE_IP  (e.g. 192.168.100.1)
    Target machine: CLIENT_IP  (e.g. 192.168.100.2)
    """

    SOURCE_IP    = "192.168.100.1"
    CLIENT_IP    = "192.168.100.2"
    SUBNET_MASK  = "255.255.255.0"
    LEASE_TIME   = 86400  # 24 hours
    TFTP_BOOT    = "pxelinux.0"

    def __init__(self, bind_ip: str = "0.0.0.0",
                 source_ip: Optional[str] = None,
                 client_ip: Optional[str] = None,
                 tftp_boot_file: Optional[str] = None):
        self.bind_ip      = bind_ip
        self.source_ip    = source_ip or self.SOURCE_IP
        self.client_ip    = client_ip or self.CLIENT_IP
        self.boot_file    = tftp_boot_file or self.TFTP_BOOT
        self._stop        = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._sock: Optional[socket.socket] = None

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="DHCPServer")
        self._thread.start()
        logger.info(f"DHCP server started on port {DHCP_SERVER_PORT}. Client IP: {self.client_ip}")

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
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(1.0)
            sock.bind((self.bind_ip, DHCP_SERVER_PORT))
            self._sock = sock
            logger.info("DHCP server listening...")

            while not self._stop.is_set():
                try:
                    data, addr = sock.recvfrom(2048)
                    self._handle_packet(sock, data, addr)
                except socket.timeout:
                    continue
                except OSError:
                    break
        except Exception as e:
            logger.error(f"DHCP server error: {e}")

    def _handle_packet(self, sock: socket.socket, data: bytes, addr):
        if len(data) < 240:
            return

        # Parse DHCP packet header
        op, htype, hlen, hops = struct.unpack_from("BBBB", data, 0)
        xid = struct.unpack_from("!I", data, 4)[0]
        mac = data[28:28 + hlen]
        mac_str = _mac_to_str(mac)

        # Parse options
        options_data = data[236:]
        if not options_data.startswith(MAGIC_COOKIE):
            return
        options = _parse_options(options_data[4:])

        msg_type = options.get(OPT_MSG_TYPE, b"\x00")[0]

        if msg_type == DHCPDISCOVER:
            logger.info(f"DHCPDISCOVER from {mac_str}")
            self._send_offer(sock, xid, mac, data)
        elif msg_type == DHCPREQUEST:
            logger.info(f"DHCPREQUEST from {mac_str}")
            self._send_ack(sock, xid, mac, data)

    def _build_reply(self, xid: int, mac: bytes, client_ip: str, options_bytes: bytes) -> bytes:
        # BOOTP header
        header = struct.pack(
            "!BBBBIH HI4s4s4s4s",
            2,        # op: BOOTREPLY
            1,        # htype: Ethernet
            6,        # hlen
            0,        # hops
            xid,
            0,        # secs
            0x8000,   # flags: broadcast
            0,        # ciaddr
            socket.inet_aton(client_ip),  # yiaddr
            socket.inet_aton(self.source_ip),  # siaddr (TFTP server)
            socket.inet_aton("0.0.0.0"),  # giaddr
            mac[:6].ljust(16, b"\x00"),  # chaddr (16 bytes)
        )
        # sname (64 bytes) + file (128 bytes)
        boot_file = self.boot_file.encode().ljust(128, b"\x00")
        padding = b"\x00" * 64  # sname
        return header + padding + boot_file + MAGIC_COOKIE + options_bytes

    def _send_offer(self, sock: socket.socket, xid: int, mac: bytes, _orig: bytes):
        opts = (
            _pack_option(OPT_MSG_TYPE,   bytes([DHCPOFFER])) +
            _pack_option(OPT_SERVER_ID,  _ip_to_bytes(self.source_ip)) +
            _pack_option(OPT_LEASE_TIME, struct.pack("!I", self.LEASE_TIME)) +
            _pack_option(OPT_SUBNET_MASK, _ip_to_bytes(self.SUBNET_MASK)) +
            _pack_option(OPT_ROUTER,     _ip_to_bytes(self.source_ip)) +
            _pack_option(OPT_TFTP_SERVER, self.source_ip.encode()) +
            _pack_option(OPT_BOOTFILE,   self.boot_file.encode()) +
            bytes([OPT_END])
        )
        pkt = self._build_reply(xid, mac, self.client_ip, opts)
        sock.sendto(pkt, (BROADCAST_IP, DHCP_CLIENT_PORT))
        logger.info(f"DHCPOFFER sent: {self.client_ip}")

    def _send_ack(self, sock: socket.socket, xid: int, mac: bytes, _orig: bytes):
        opts = (
            _pack_option(OPT_MSG_TYPE,   bytes([DHCPACK])) +
            _pack_option(OPT_SERVER_ID,  _ip_to_bytes(self.source_ip)) +
            _pack_option(OPT_LEASE_TIME, struct.pack("!I", self.LEASE_TIME)) +
            _pack_option(OPT_SUBNET_MASK, _ip_to_bytes(self.SUBNET_MASK)) +
            _pack_option(OPT_ROUTER,     _ip_to_bytes(self.source_ip)) +
            _pack_option(OPT_TFTP_SERVER, self.source_ip.encode()) +
            _pack_option(OPT_BOOTFILE,   self.boot_file.encode()) +
            bytes([OPT_END])
        )
        pkt = self._build_reply(xid, mac, self.client_ip, opts)
        sock.sendto(pkt, (BROADCAST_IP, DHCP_CLIENT_PORT))
        logger.info(f"DHCPACK sent: {self.client_ip}")
