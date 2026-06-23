"""
world_entry.py — Character selection and world entry replay sequence.

The 13-step handshake that gets the client from "logged in" 
to "standing in the game world with an active session".
Also includes the warp handshake for map transitions.
"""
import binascii
import time

from core.packet_helpers import hex_recv, hex_send
from core.game_state import state
from core.packets import (
    PKT_CHAR_SELECT, PKT_ENTER_WORLD, PKT_POST_MAP,
    PKT_MOVEMENT_STEPS, PKT_MOVEMENT_READY,
    PKT_PRESENCE_START, PKT_MAP_SYNC_BEGIN, PKT_BULK_HEADER,
    PKT_MOTION_TRIGGER, PKT_VISUALS_SETUP, PKT_WORLD_TICKS,
    PRESENCE_ZEROS, build_map_data_packet, build_bulk_data_packet,
    build_world_ticks_packet,
    PKT_WARP_SYNC_START, PKT_WARP_SYNC_END,
    build_warp_exit_packet, build_warp_position_packet, build_warp_entry_packet,
    PKT_SUMMON_PET,
)
from core.map_teleport import get_map_name

# Default spawn — Miscerene Plains (Map 012c)
DEFAULT_MAP  = "012c"
DEFAULT_X    = "00004700"
DEFAULT_Y    = "00001000"


def _send_and_log(sock, pkt_hex, label=None, delay=0.1):
    """Send a hex packet and pause briefly for server processing."""
    hex_send(sock, pkt_hex, label=label)
    time.sleep(delay)


def _parse_spawn_coords(data: bytes):
    """
    Extract spawn coordinates from the b503 map sync packet
    embedded in the server's 'Extra State Data' response.
    
    The b503 payload layout (13 bytes):
      [3 skip][2 map][2 skip][2 raw_x][2 skip][2 raw_y]
    Coords are shifted left by 8 bits to match the client format.
    """
    h = binascii.hexlify(data).decode()
    idx = h.find("b503")
    if idx == -1:
        print("[-] No b503 sync found in login data, keeping defaults")
        return
    
    # b503 payload starts right after the 4-char opcode
    payload_hex = h[idx + 4:]
    if len(payload_hex) < 26:  # need 13 bytes (26 hex chars) of payload
        print("[-] b503 payload too short, keeping defaults")
        return
    
    try:
        payload = binascii.unhexlify(payload_hex[:26])
        raw_map = binascii.hexlify(payload[3:5]).decode()
        raw_x = int.from_bytes(payload[7:9], "big")
        raw_y = int.from_bytes(payload[11:13], "big")
        shifted_x = format((raw_x << 8) & 0xFFFF, '04x')
        shifted_y = format((raw_y << 8) & 0xFFFF, '04x')
        state.last_map_coords = shifted_x + shifted_y
        state.current_map_hex = raw_map
        state.map_name = get_map_name(int(raw_map, 16))
        print(f"[+] Spawn coords from server (b503): Map {raw_map} | Coords {shifted_x}{shifted_y}")
    except Exception as e:
        print(f"[-] Failed to parse b503 coords: {e}")

def _extract_0111_spawn(data_hex: str):
    """
    Extract the initial saved map & spawn coords from the character info payload.
    The packet is embedded inside the large response to 0001 (Enter World).
    Format: [length]01110000[map_hex][x_shifted][y_shifted]0000...
    """
    idx = data_hex.find("0a01110000")
    if idx == -1:
        return False
        
    try:
        # The payload is exactly after "0a01110000"
        payload = data_hex[idx + 10 : idx + 10 + 12] # 4 chars map, 4 chars x, 4 chars y
        if len(payload) == 12:
            map_hex = payload[:4]
            x_shifted = payload[4:8]
            y_shifted = payload[8:12]
            state.current_map_hex = map_hex
            state.last_map_coords = x_shifted + y_shifted
            state.map_name = get_map_name(int(map_hex, 16))
            print(f"[+] Found saved spawn from 0111: Map {map_hex} | Coords {x_shifted}{y_shifted}")
            return True
    except Exception as e:
        pass
    return False


def enter_world(sock, char_id_hex: str):
    """
    Run the full character-select → world-entry → presence-confirm
    replay sequence (13 steps).
    
    This must be called after a successful login (connect_and_login).
    
    Args:
        sock: Connected & authenticated socket
        char_id_hex: 8-char hex string of the character ID
    """
    # We will accumulate all received hex data to ensure we don't miss 0111 split across reads
    login_buffer = ""

    # Step 4: Character Select
    _send_and_log(sock, PKT_CHAR_SELECT, "Character Select")
    char_sel = hex_recv(sock, label="Character Info")
    if char_sel: login_buffer += binascii.hexlify(char_sel).decode()

    # Step 5: Enter World — send opcode + char_id separately
    _send_and_log(sock, PKT_ENTER_WORLD, "Enter World")
    _send_and_log(sock, char_id_hex, "Character ID")
    char_info_1 = hex_recv(sock, label="Character Info")
    if char_info_1: login_buffer += binascii.hexlify(char_info_1).decode()

    # Step 6: Post-Map — send opcode + char_id separately
    _send_and_log(sock, PKT_POST_MAP, "Post-Map")
    _send_and_log(sock, char_id_hex, "Character ID Repeat")
    char_info_2 = hex_recv(sock, label="Character Info")
    if char_info_2: login_buffer += binascii.hexlify(char_info_2).decode()

    # Step 7: Movement Handshake (4 steps + ready)
    for step in PKT_MOVEMENT_STEPS:
        _send_and_log(sock, step, "Movement Step")
    pre_move_sync = hex_recv(sock, label="Pre-Movement Sync")
    if pre_move_sync: login_buffer += binascii.hexlify(pre_move_sync).decode()

    _send_and_log(sock, PKT_MOVEMENT_READY, "Movement Step")
    move_sync = hex_recv(sock, label="Movement Sync")
    if move_sync: login_buffer += binascii.hexlify(move_sync).decode()

    # Look for 0111 to override default spawn before we send 0110!
    _extract_0111_spawn(login_buffer)

    # Step 8: Presence Start — header + 25 zero bytes
    _send_and_log(sock, PKT_PRESENCE_START, "Presence Start")
    _send_and_log(sock, PRESENCE_ZEROS, "Zeroes")

    # Step 9: Map Location — sync begin + map data
    _send_and_log(sock, PKT_MAP_SYNC_BEGIN, "Map Location Begin")
    
    # Use the extracted coordinates instead of hardcoded defaults!
    map_data = build_map_data_packet(
        state.current_map_hex, 
        state.last_map_coords[:4], 
        state.last_map_coords[4:]
    )
    _send_and_log(sock, map_data, "Map Data")
    hex_recv(sock, label="Ack for Position")

    # Step 10: Resend Position — server responds with b503 containing spawn coords
    _send_and_log(sock, PKT_MAP_SYNC_BEGIN, "Resend Position")
    extra_data = hex_recv(sock, label="Extra State Data")
    _parse_spawn_coords(extra_data)

    # Step 11: Bulk Action
    _send_and_log(sock, PKT_BULK_HEADER, "Bulk Action")
    bulk_data = build_bulk_data_packet(state.current_map_hex)
    _send_and_log(sock, bulk_data, "Bulk Action Contd.")

    # Step 12: Trigger Motion
    _send_and_log(sock, PKT_MOTION_TRIGGER, "Trigger Motion")
    motion_ack = hex_recv(sock, label="Motion Ack")
    if motion_ack:
        _extract_0111_spawn(binascii.hexlify(motion_ack).decode())

    # Step 13: Visuals + World Ticks
    _send_and_log(sock, PKT_VISUALS_SETUP, "Visuals Setup")
    _send_and_log(sock, PKT_WORLD_TICKS, "World Ticks Start")
    _send_and_log(sock, build_world_ticks_packet(), "World Ticks")

    hex_recv(sock, label="Server Update")

    # current_map_hex already set by _parse_spawn_coords from b503

    # Step 14: Summon Pet
    import re
    # The pet structure in the character info packet is typically: 
    # [UID (8 hex chars)] 0064 [Name Length (4 hex chars)] [Name]
    pet_match = re.search(r"([0-9a-f]{8})006400[0-9a-f]{2}", login_buffer, re.IGNORECASE)
    if pet_match:
        state.pet_uid_hex = pet_match.group(1)
        print(f"[+] Found Pet! UID: {state.pet_uid_hex}")
        _send_and_log(sock, PKT_SUMMON_PET, "Summon Pet Opcode")
        _send_and_log(sock, state.pet_uid_hex, "Summon Pet UID")
    else:
        print("[-] No pets found in login sequence.")


def warp_to_map(sock, target_map: str, portal_id: str, x: str, y: str):
    """
    The 3002 sandwich warp — universal map transition handshake.
    
    Ported from iruna_engine.py's warp_handshake().
    
    Args:
        sock: Active game socket
        target_map: 4-char hex map ID (e.g. "0190" for map 400)
        portal_id: 2-char hex portal identifier
        x: X coordinate hex
        y: Y coordinate hex
    """
    print(f"[*] Warping to Map {target_map} via Portal {portal_id}")
    
    # Departure
    exit_pkt = build_warp_exit_packet(portal_id, state.current_map_hex)
    _send_and_log(sock, exit_pkt, "3002 EXIT")
    
    # Transition Load
    _send_and_log(sock, PKT_WARP_SYNC_START, "3006 SYNC START")
    
    # Position prediction
    pos_pkt = build_warp_position_packet(target_map, x, y)
    _send_and_log(sock, pos_pkt, "110 POSITION")
    
    # Arrival
    _send_and_log(sock, PKT_WARP_SYNC_END, "3006 SYNC END")
    entry_pkt = build_warp_entry_packet(target_map)
    _send_and_log(sock, entry_pkt, "3002 ENTRY")
    
    # Update state
    state.current_map_hex = target_map
    state.last_map_coords = f"{x}00{y}00"
