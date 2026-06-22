"""
map_teleport.py -- Direct map teleportation via the 0110 opcode.

Unlike warp_to_map() which uses portal-based 3002 sandwiches,
this module performs DIRECT teleportation: send 0110 position packet,
wait for b503 confirmation, then send 013a + 3002 entry.

Also loads Area.sql (if present) for map name lookup.

Teleport sequence (from proxy captures):
  1. C->S: 000e0110 0000{map}{x_shifted}{y_shifted}   (0110 position)
  2. S->C: b503 confirm (map + coords)
  3. S->C: 0240 + 0138 (state data)
  4. C->S: 0002013a                                     (map sync begin)
  5. C->S: 000f3002 1100000000000000000000{map}          (3002 entry)
  6. S->C: 013a ack + 3002 ack + 3003 map data
  7. C->S: 00060101 {coords}                             (coord heartbeat)
"""
import os
import time
import sqlite3
import binascii

from core.game_state import state
from core.game_state import state
from core.packet_helpers import hex_send
from core.packets import (
    PKT_MAP_SYNC_BEGIN, PKT_COORD_PREFIX,
    PKT_WARP_SYNC_START, PKT_WARP_SYNC_END,
    build_map_data_packet, build_warp_entry_packet,
    build_warp_exit_packet
)


# ════════════════════════════════════════════
#  AREA DATABASE (from Area.sql)
# ════════════════════════════════════════════

_area_db = {}       # {area_id_int: name_str}
_area_db_loaded = False

# Default center coordinates when exact spawn is unknown
# Map coords range 0-156 for x and y, centre ~ 78 = 0x4E
DEFAULT_CENTER_X = 0x4E
DEFAULT_CENTER_Y = 0x4E


def load_area_db():
    """Load area/map names from Area.sql into memory. Non-fatal if missing."""
    global _area_db, _area_db_loaded

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sql_path = os.path.join(base_dir, "Area.sql")

    if not os.path.exists(sql_path):
        print("[*] Area.sql not found -- teleport will use raw map IDs")
        return

    try:
        with open(sql_path, "r", encoding="utf-8", errors="ignore") as f:
            sql_content = f.read()

        conn = sqlite3.connect(":memory:")
        conn.executescript(sql_content)
        cursor = conn.execute("SELECT AreaID, Name FROM Area")
        for row in cursor.fetchall():
            _area_db[row[0]] = row[1]
        conn.close()
        _area_db_loaded = True
        print(f"[+] Area DB loaded: {len(_area_db)} maps from Area.sql")
    except Exception as e:
        print(f"[-] Failed to load Area DB: {e}")


def get_map_name(area_id: int) -> str:
    """Get map name by decimal AreaID."""
    return _area_db.get(area_id, f"Unknown(0x{area_id:04X})")


def find_map_by_name(query: str) -> list:
    """
    Search for maps matching a query string (case-insensitive).
    Returns list of (area_id, name) tuples.
    """
    query_lower = query.lower()
    results = []
    for aid, name in _area_db.items():
        if query_lower in name.lower():
            results.append((aid, name))
    return sorted(results, key=lambda x: x[0])


# ════════════════════════════════════════════
#  COORDINATE HELPERS
# ════════════════════════════════════════════

def _make_shifted_coord(raw_coord: int) -> str:
    """
    Convert a raw map coordinate (0-156) to the 2-byte shifted hex string.
    The client protocol shifts coordinates left by 8 bits.
    
    Example: raw 0x57 -> shifted 0x5700 -> "5700"
    """
    shifted = (raw_coord << 8) & 0xFFFF
    return f"{shifted:04x}"


def _make_heartbeat_coords(x: int, y: int) -> str:
    """
    Build the 4-byte coordinate string for heartbeat packets.
    Format: XX00YY00 where XX/YY are the shifted values.
    
    Example: x=0x57, y=0x5c -> "57005c00"
    """
    return f"{(x << 8) & 0xFFFF:04x}{(y << 8) & 0xFFFF:04x}"


# ════════════════════════════════════════════
#  TELEPORT FUNCTION
# ════════════════════════════════════════════

def teleport(sock, map_id: int, x: int = None, y: int = None):
    """
    Teleport directly to a map using the 0110 opcode sequence.
    
    Args:
        sock:   Active game socket
        map_id: Decimal AreaID (e.g. 25100 for Kakeula City)
        x:      Raw X coordinate (0-156). Defaults to center (78).
        y:      Raw Y coordinate (0-156). Defaults to center (78).
    """
    if x is None:
        x = DEFAULT_CENTER_X
    if y is None:
        y = DEFAULT_CENTER_Y

    # Clamp coordinates to valid range
    x = max(0, min(156, x))
    y = max(0, min(156, y))

    map_hex = f"{map_id:04x}"
    x_shifted = _make_shifted_coord(x)
    y_shifted = _make_shifted_coord(y)
    heartbeat_coords = _make_heartbeat_coords(x, y)

    # Pause navigation heartbeat so it doesn't interrupt the transition sequence
    was_paused = state.paused
    state.paused = True

    try:
        # Resolve name for logging
        name = get_map_name(map_id)
        
        # Step 1: Request New Position
        state.teleport_event.clear()
        state.map_ready_event.clear()
        state.map_data_event.clear()
        pos_pkt = build_map_data_packet(map_hex, x_shifted, y_shifted)
        hex_send(sock, pos_pkt, label="0110 TELEPORT")

        # Wait for b503 Map Sync success
        if state.teleport_event.wait(timeout=5.0):
            if state.teleport_success:
                print(f"[+] Server confirmed map {name} (0x{map_hex}). Waiting for 0138 (Ready)...")
                
                # Wait for 0138
                if state.map_ready_event.wait(timeout=5.0):
                    print(f"[+] TELEPORTED to {name} (0x{map_hex}) | Coords: {x_shifted}{y_shifted}")
                    
                    # Step 2: 013a Map Sync
                    time.sleep(0.1)
                    hex_send(sock, PKT_MAP_SYNC_BEGIN, label="013a Map Sync")
                    
                    # Step 3: 3002 entry packet using the map confirmed by server
                    entry_pkt = build_warp_entry_packet(state.current_map_hex)
                    hex_send(sock, entry_pkt, label="3002 ENTRY")

                    # Step 4: Wait for 3003 Map Data before resuming coordinates
                    if state.map_data_event.wait(timeout=5.0):
                        print("[+] Received 3003 Map Data. Map entry complete.")
                    else:
                        print("[-] Timeout waiting for 3003 Map Data, resuming anyway.")

                    return {"status": "success", "map_id": map_id, "x": x, "y": y}
                else:
                    print("[-] Teleport timeout. Did not receive 0138 Map Ready from server.")
                    return
            else:
                print("[-] Teleport REJECTED by server (b505). Aborting map entry sequence.")
                return

        print("[-] Teleport timeout. Did not receive b503 Map Sync from server.")
        return
            
    finally:
        # Resume navigation heartbeat if it was running before
        state.paused = was_paused


# ════════════════════════════════════════════
#  CONVENIENCE: KNOWN MAP PRESETS
# ════════════════════════════════════════════
# Add frequently used teleport targets here for quick access.

KNOWN_MAPS = {
    "kakeula":    {"id": 25100, "x": 0x57, "y": 0x5C, "name": "Kakeula City"},
    "zimov_boss": {"id": 15900, "x": 0x43, "y": 0x80, "name": "Zimov Boss Map"},
    "micerne":    {"id": 300,   "x": 0x47, "y": 0x10, "name": "Micerne Plains"},
    "bailune":    {"id": 200,   "x": 0x4E, "y": 0x4E, "name": "Bailune City"},
    "rokoko":     {"id": 700,   "x": 0x4E, "y": 0x4E, "name": "Rokoko City"},
    "sofya":      {"id": 3200,  "x": 0x4E, "y": 0x4E, "name": "Capital Sofya"},
}


def teleport_preset(sock, preset_name: str):
    """
    Teleport to a named preset location.
    
    Args:
        sock: Active game socket
        preset_name: Key from KNOWN_MAPS (e.g. "kakeula", "zimov_boss")
    """
    preset = KNOWN_MAPS.get(preset_name.lower())
    if not preset:
        available = ", ".join(KNOWN_MAPS.keys())
        print(f"[-] Unknown preset '{preset_name}'. Available: {available}")
        return
    
    teleport(sock, preset["id"], preset["x"], preset["y"])
