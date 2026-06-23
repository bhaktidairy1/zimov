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
_log_filepath = None
_log_lines = 0


def start_packet_log(log_dir=None):
    """
    Start logging all packets to a timestamped file.
    Call this after login to capture the full game session.
    """
    global _log_file, _log_filepath, _log_lines
    if log_dir is None:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        log_dir = os.path.join(base_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    _log_filepath = os.path.join(log_dir, f"packet_log_{timestamp}.txt")
    
    _log_file = open(_log_filepath, "a", encoding="utf-8")
    _log_file.write(f"=== Packet Log Started: {datetime.datetime.now()} ===\n")
    _log_file.flush()
    _log_lines = 0
    print(f"[+] Packet logging to: {_log_filepath}")
    return _log_filepath


def stop_packet_log():
    """Close the log file."""
    global _log_file
    if _log_file:
        _log_file.write(f"=== Packet Log Ended: {datetime.datetime.now()} ===\n")
        _log_file.close()
        _log_file = None


def write_log(line: str):
    """Write a line to the packet log file (if logging is active)."""
    global _log_file, _log_lines, _log_filepath
    if _log_file:
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        _log_file.write(f"[{ts}] {line}\n")
        _log_file.flush()
        _log_lines += 1
        
        import sys
        if "--minimal" in sys.argv and _log_lines >= 1000:
            # Rotate log in minimal mode to prevent massive disk usage
            _log_file.close()
            backup_path = _log_filepath + ".1"
            import os
            if os.path.exists(backup_path):
                try: os.remove(backup_path)
                except: pass
            try: os.rename(_log_filepath, backup_path)
            except: pass
            
            _log_file = open(_log_filepath, "w", encoding="utf-8")
            _log_file.write(f"=== Packet Log Rolled Over: {datetime.datetime.now()} ===\n")
            _log_lines = 0


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
        
    import sys
    if "--minimal" not in sys.argv:
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
        
    import sys
    if "--minimal" not in sys.argv:
        print(msg)
    write_log(msg)
