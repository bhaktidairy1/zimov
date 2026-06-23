"""
combat.py — Combat engine and coordinate heartbeat threads.

Two daemon threads:
  - coordinate_sender: sends position updates every 1s
  - combat_engine: auto-attack loop with target selection
"""
import time

from core.game_state import state
from core.packet_helpers import hex_send
from core.packets import build_attack_packet, build_coord_packet


def coordinate_sender(sock):
    """
    Heartbeat loop — sends 0101 position packet every 1 second.
    Every 10 seconds, sends a 0002ffff check-alive and waits for a response (up to 5s).
    
    If targeting a monster, uses the monster's position instead
    of the player's last known coords (moves toward target).
    Pauses when state.paused is True (safe for manual warping).
    """
    import os
    ticks = 0
    while not state.stop_event.is_set():
        if state.paused or state.in_scripted_sequence:
            time.sleep(0.5)
            continue
            
        ticks += 1
        try:
            if ticks % 10 == 0:
                # 10-second check-alive heartbeat
                state.check_alive_event.clear()
                hex_send(sock, "0002ffff", label="STANDBY KEEP-ALIVE")
                
                # Wait for response, blocking coordinate sends during this wait
                if not state.check_alive_event.wait(timeout=5.0):
                    print("[-] Keep-Alive timeout (0002ffff). Server unresponsive in standby. Exiting.")
                    try: sock.close()
                    except: pass
                    os._exit(1)
            else:
                # Regular coordinate send
                current_pos = state.last_map_coords
                if state.target_uid and state.target_uid in state.monsters:
                    m = state.monsters[state.target_uid]
                    current_pos = m['x'] + m['y']
                hex_send(sock, build_coord_packet(current_pos))
        except:
            break
            
        time.sleep(1.0)


def combat_engine(sock):
    """
    Auto-attack loop — sends attack packets when in AUTO or MANUAL mode.
    
    Modes:
      - STANDBY: Do nothing, clear target
      - AUTO: Automatically pick the nearest valid monster and attack
      - MANUAL: Attack only the manually selected target
      
    Uses state.waiting_for_hit event to pace attacks 
    (waits for server hit confirmation before next swing).
    """
    while not state.stop_event.is_set():
        if state.paused:
            time.sleep(0.5)
            continue
            
        if state.mode == "STANDBY":
            state.target_uid = None
            time.sleep(0.5)
            continue
            
        if state.target_uid and state.target_uid in state.monsters:
            # Attack current target
            attack_pkt = build_attack_packet(state.target_uid)
            state.waiting_for_hit.clear()
            hex_send(sock, attack_pkt)
            state.waiting_for_hit.wait(timeout=0.8)
            time.sleep(0.4)
            
        elif state.mode == "AUTO":
            # Auto-select a target from known monsters
            for uid, data in state.monsters.items():
                if data['id'] in [0, 1, 2]:
                    state.target_uid = uid
                    break
            time.sleep(0.2)
            
        else:
            time.sleep(0.5)
