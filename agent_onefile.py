"""
OmniClone Agent - Debug Version
"""

import socket
import struct
import json
import subprocess
import time

MAGIC = b"OMNI"
HEADER_SIZE = 16
AGENT_PORT = 9876
SOURCE_IP = "192.168.100.1"

MSG_HELLO = 1
MSG_PARTITION_LIST = 2
MSG_SELECT_TARGET = 3
MSG_SELECT_ACK = 4

def pack_message(msg_type, payload):
    header = struct.pack("!4sBBHQ", MAGIC, 1, msg_type, 0, len(payload))
    return header + payload

def unpack_header(data):
    magic, version, msg_type, flags, length = struct.unpack("!4sBBHQ", data[:16])
    return msg_type, length

def encode_json(obj):
    return json.dumps(obj).encode()

def decode_json(data):
    return json.loads(data.decode())

def scan_partitions():
    partitions = []
    result = subprocess.run(["diskpart"], input="list volume\nexit\n", 
                           capture_output=True, text=True, timeout=10)
    for line in result.stdout.splitlines():
        if "Volume" in line:
            parts = line.split()
            for p in parts:
                if len(p) == 1 and p.isalpha() and p not in "XYZ":
                    partitions.append({"letter": p, "label": "", "fs": "NTFS",
                                      "size_bytes": 0, "used_bytes": 0,
                                      "device_path": f"\\\\.\\{p}:",
                                      "partition_index": 0, "disk_index": 0,
                                      "offset_bytes": 0, "is_system": p == "C",
                                      "is_active": False})
                    break
    return partitions

def recv_exact(sock, n, timeout=30):
    sock.settimeout(timeout)
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError()
        buf.extend(chunk)
    return bytes(buf)

def main():
    print("=== Agent Debug Starting ===")
    
    # Connect
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    print(f"Connecting to {SOURCE_IP}:{AGENT_PORT}...")
    
    for i in range(5):
        try:
            sock.connect((SOURCE_IP, AGENT_PORT))
            print("Connected!")
            break
        except Exception as e:
            print(f"Attempt {i+1} failed: {e}")
            time.sleep(2)
    else:
        print("Failed to connect after 5 attempts")
        input("Press Enter...")
        return
    
    # Send HELLO
    sock.sendall(pack_message(MSG_HELLO, encode_json({"hostname": "WinPE"})))
    print("Sent HELLO")
    
    # Send partitions
    partitions = scan_partitions()
    print(f"Found {len(partitions)} partitions: {[p['letter'] for p in partitions]}")
    sock.sendall(pack_message(MSG_PARTITION_LIST, encode_json(partitions)))
    print("Sent partition list")
    
    # Wait for SELECT_TARGET (THIS IS THE CRITICAL PART)
    print("Waiting for SELECT_TARGET from source...")
    print("Make sure you selected both partitions and clicked 'Start Clone' on source!")
    
    try:
        header = recv_exact(sock, 16, timeout=60)
        msg_type, length = unpack_header(header)
        print(f"Received message type: {msg_type}, length: {length}")
        
        if msg_type == MSG_SELECT_TARGET:
            payload = recv_exact(sock, length)
            target = decode_json(payload)
            print(f"SUCCESS! Target selected: {target['letter']}:")
            
            # Send ACK
            sock.sendall(pack_message(MSG_SELECT_ACK, encode_json({"success": True})))
            print("Sent ACK, ready to receive data...")
        else:
            print(f"Wrong message type! Expected 3, got {msg_type}")
            
    except socket.timeout:
        print("TIMEOUT! Source did not send SELECT_TARGET")
        print("Check that:")
        print("1. You selected source partition (left side)")
        print("2. You selected target partition (right side)")
        print("3. You clicked 'Start Clone' button")
        print("4. Firewall is disabled on source")
    except Exception as e:
        print(f"Error: {e}")
    
    print("Debug session complete")
    input("Press Enter to exit...")

if __name__ == "__main__":
    main()