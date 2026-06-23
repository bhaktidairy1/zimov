"""
receiver.py — Continuous packet receiver with opcode dispatch.

Runs as a daemon thread. Reads the TCP stream, parses packets
using the 4-byte length header + 2-byte opcode format, and 
dispatches to registered handler functions.
"""
import socket
import binascii

from core.game_state import state
from core.packets import (
    OP_MAP_SYNC, OP_MAP_SYNC_B505, OP_MOB_SPAWN, OP_ENTITY_DEATH, OP_HIT_CONFIRM,
    OP_INVENTORY, OP_ITEM_DROP, OP_INV_UPDATE, OP_MAP_READY, OP_MAP_DATA,
)
from core.map_teleport import get_map_name
from core.packet_helpers import write_log
from core.inventory import (
    handle_item_drop, handle_inventory_update, handle_full_inventory,
)


# ════════════════════════════════════════════
#  OPCODE HANDLERS
# ════════════════════════════════════════════

def handle_map_sync_b503(payload: bytes):
    _handle_map_sync_internal(payload, success=True)

def handle_map_sync_b505(payload: bytes):
    _handle_map_sync_internal(payload, success=False)

def _handle_map_sync_internal(payload: bytes, success: bool):
    """
    Opcode 0xb503 or 0xb505 — Server forces a position sync.
    Parses map ID, X, Y from the payload and updates state.
    Clears existing monsters since we are in a new location.
    """
    try:
        raw_map = binascii.hexlify(payload[3:5]).decode()
        raw_x = int.from_bytes(payload[5:9], "big")
        raw_y = int.from_bytes(payload[9:13], "big")
        
        if raw_x < 256:
            shifted_x = format((raw_x << 8) & 0xFFFF, '04x')
        else:
            shifted_x = format(raw_x & 0xFFFF, '04x')
            
        if raw_y < 256:
            shifted_y = format((raw_y << 8) & 0xFFFF, '04x')
        else:
            shifted_y = format(raw_y & 0xFFFF, '04x')

        state.current_map_hex = raw_map
        state.last_map_coords = shifted_x + shifted_y
        state.map_name = get_map_name(int(raw_map, 16))
        
        # Clear out old entities
        state.monsters.clear()
        state.target_uid = None
        
        # Signal any waiting teleport routine
        state.teleport_success = success
        state.teleport_event.set()
        
        status = "SUCCESS" if success else "REJECTED/OVERRIDE"
        print(f"\n[!] MAP SYNC ({status}): Map {raw_map} | Coords {shifted_x}{shifted_y}")
    except Exception as e:
        print(f"[!] Sync Parse Error: {e}")


def handle_mob_spawn(payload: bytes):
    """
    Opcode 0x0245 — Monster/NPC spawned.
    Extracts UID, monster ID, and position.
    """
    uid = binascii.hexlify(payload[0:4]).decode()
    m_id = int.from_bytes(payload[4:6], "big")
    state.monsters[uid] = {
        'id': m_id,
        'x': binascii.hexlify(payload[6:7]).decode() + "00",
        'y': binascii.hexlify(payload[8:9]).decode() + "00",
    }
    
    # Catch boss spawns dynamically during sequences
    if state.in_scripted_sequence:
        # Zimov spawn is usually caught here
        state.boss_id_hex = uid
        state.boss_spawn_event.set()


def handle_entity_death(payload: bytes):
    """
    Opcode 0x0244 — Entity died/despawned.
    Removes from monster tracker. Clears target if it was our target.
    """
    uid = binascii.hexlify(payload[0:4]).decode()
    if uid in state.monsters:
        del state.monsters[uid]
    if state.target_uid == uid:
        state.target_uid = None
        
    if state.in_scripted_sequence and uid == state.boss_id_hex:
        state.boss_death_event.set()


def handle_hit_confirm(payload: bytes):
    """
    Opcode 0x0241 — Attack hit confirmed by server.
    Signals the combat engine to continue the attack cycle.
    """
    state.waiting_for_hit.set()

def handle_map_ready(payload: bytes):
    """
    Opcode 0x0138 — Server is ready for Map Sync (013a).
    """
    state.map_ready_event.set()

def handle_map_data(payload: bytes):
    """
    Opcode 0x3003 — Final Map Sync ACK from Server.
    """
    state.map_data_event.set()

# ════════════════════════════════════════════
#  HANDLER REGISTRY
# ════════════════════════════════════════════
# Add new opcode handlers here — no need to touch the receiver loop.

HANDLERS = {
    0xffff: lambda p: state.check_alive_event.set(),
    OP_MAP_SYNC:        handle_map_sync_b503,
    OP_MAP_SYNC_B505:   handle_map_sync_b505,
    OP_MOB_SPAWN:       handle_mob_spawn,
    OP_ENTITY_DEATH:    handle_entity_death,
    OP_HIT_CONFIRM:     handle_hit_confirm,
    OP_INVENTORY:       handle_full_inventory,
    OP_ITEM_DROP:       handle_item_drop,
    OP_INV_UPDATE:      handle_inventory_update,
    OP_MAP_READY:       handle_map_ready,
    OP_MAP_DATA:        handle_map_data,
}


# ════════════════════════════════════════════
#  RECEIVER THREAD
# ════════════════════════════════════════════

def continuous_receiver(sock: socket.socket):
    """
    Buffer-based packet reader. Runs in a daemon thread.
    
    Protocol format:
      [4-byte length] [2-byte opcode] [payload...]
      Total packet size = length + 4
      
    Dispatches recognized opcodes to HANDLERS dict.
    Logs all packets for debugging.
    """
    buffer = b""
    print("[*] Receiver Thread: Online and Listening...")
    
    while not state.stop_event.is_set():
        try:
            data = sock.recv(4096)
            if not data:
                print("\n[!!!] SERVER DISCONNECTED")
                break
            
            buffer += data
            
            while len(buffer) >= 6:
                pkt_len = int.from_bytes(buffer[0:4], "big")
                opcode = int.from_bytes(buffer[4:6], "big")
                total_pkt_size = pkt_len + 4
                
                # Safety: skip junk length headers
                if pkt_len > 10000 or pkt_len == 0:
                    buffer = buffer[1:]
                    continue
                
                # Wait for full packet
                if len(buffer) < total_pkt_size:
                    break
                
                raw_packet = buffer[:total_pkt_size]
                payload = buffer[6:total_pkt_size]
                
                # Log every packet (console + file)
                opcode_hex = hex(opcode)
                log_line = f"← [RECV] {opcode_hex} | {binascii.hexlify(raw_packet).decode()}"
                print(log_line)
                write_log(log_line)
                
                # Dispatch to handler if registered
                handler = HANDLERS.get(opcode)
                if handler:
                    handler(payload)
                
                buffer = buffer[total_pkt_size:]
                
        except socket.timeout:
            print("\n[!!!] NO SERVER RESPONSE FOR 5 SECONDS. CONNECTION DEAD. EXITING.")
            import os
            os._exit(1)
        except Exception as e:
            print(f"[CRITICAL] Error in receiver: {e}")
            break
    
    print("[*] Receiver Thread: Offline.")
