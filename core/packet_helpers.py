"""
packet_helpers.py — Low-level send/receive helpers with optional file logging.

Call start_packet_log() after login to begin writing all packets to a timestamped file.
"""
import binascii
import datetime
import os

# ════════════════════════════════════════════
#  FILE LOGGING
# ════════════════════════════════════════════

_log_file = None


def start_packet_log(log_dir=None):
    """
    Start logging all packets to a timestamped file.
    Call this after login to capture the full game session.
    """
    global _log_file
    if log_dir is None:
        log_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(log_dir, exist_ok=True)
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(log_dir, f"packet_log_{timestamp}.txt")
    
    _log_file = open(filepath, "a", encoding="utf-8")
    _log_file.write(f"=== Packet Log Started: {datetime.datetime.now()} ===\n")
    _log_file.flush()
    print(f"[+] Packet logging to: {filepath}")
    return filepath


def stop_packet_log():
    """Close the log file."""
    global _log_file
    if _log_file:
        _log_file.write(f"=== Packet Log Ended: {datetime.datetime.now()} ===\n")
        _log_file.close()
        _log_file = None


def write_log(line: str):
    """Write a line to the packet log file (if logging is active)."""
    if _log_file:
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        _log_file.write(f"[{ts}] {line}\n")
        _log_file.flush()


# ════════════════════════════════════════════
#  SEND / RECEIVE HELPERS
# ════════════════════════════════════════════

def hex_recv(sock, expect_len=4096, label=None) -> bytes:
    data = sock.recv(expect_len)
    if not data:
        raise ConnectionError("Server closed connection")
    h = binascii.hexlify(data).decode()
    if label:
        msg = f"← {label} ({len(data)} bytes): {h}"
    else:
        msg = f"← Received ({len(data)} bytes): {h}"
    print(msg)
    write_log(msg)
    return data


def hex_send(sock, hexstr: str, label=None):
    hexstr = hexstr.replace(" ", "")
    raw = binascii.unhexlify(hexstr)
    sock.sendall(raw)
    if label:
        msg = f"→ {label}: {hexstr}"
    else:
        msg = f"→ Sent: {hexstr}"
    print(msg)
    write_log(msg)
