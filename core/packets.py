"""
packets.py — Opcode constants and packet construction helpers.

All known Iruna opcodes and reusable packet builders live here.
When you discover new opcodes, add them to this file.
"""
import binascii

# ════════════════════════════════════════════
#  RECEIVE OPCODES (server → client)
# ════════════════════════════════════════════
OP_MAP_SYNC      = 0xb503   # Position auto-sync from server
OP_MAP_SYNC_B505 = 0xb505   # Alternate position sync (used in teleport)
OP_MOB_SPAWN     = 0x0245   # Monster/NPC appears
OP_ENTITY_DEATH  = 0x0244   # Entity removed (death/despawn)
OP_HIT_CONFIRM   = 0x0241   # Attack landed confirmation
OP_INVENTORY     = 0x0120   # Full inventory dump
OP_ITEM_DROP     = 0x0123   # Item received (drop / reward)
OP_INV_UPDATE    = 0x4018   # Inventory slot changed
OP_BOSS_SPAWN    = 0x0248   # Boss/special entity spawn
OP_DMG_RESULT    = 0x0142   # Skill damage result
OP_EXP_REWARD    = 0x0132   # Experience gained
OP_BOSS_DEFEAT   = 0x0249   # Boss defeated / reward trigger
OP_MAP_READY     = 0x0138   # Map ready for sync
OP_MAP_DATA      = 0x3003   # Map data (weather, BGM, final ack)

# ════════════════════════════════════════════
#  SEND OPCODES / PACKET PREFIXES (client → server)
# ════════════════════════════════════════════
PKT_INIT           = "0002fff3"
PKT_CHAR_SELECT    = "0002f032"
PKT_ENTER_WORLD    = "00060001"
PKT_POST_MAP       = "000623f3"
PKT_MOVEMENT_STEPS = ["00023300", "00023303", "00023300", "00023303"]
PKT_MOVEMENT_READY = "00026002"
PKT_PRESENCE_START = "001bb300"
PKT_MAP_SYNC_BEGIN = "0002013a"
PKT_BULK_HEADER    = "000f3002"
PKT_MOTION_TRIGGER = "0002016000028100000281100002830000028200"
PKT_VISUALS_SETUP  = "0003840400"
PKT_WORLD_TICKS    = "00025003"
PKT_COORD_PREFIX   = "00060101"
PKT_ATTACK_PREFIX  = "000a0241"
PKT_INVENTORY_REQ  = "00020120"   # Fetch full inventory (send ONCE)

# Warp sequence
PKT_WARP_SYNC_START = "0003300601"
PKT_WARP_SYNC_END   = "0003300600"

# Padding constants
# Presence/world-ticks packets: length 0x001b = 27, minus 2 for opcode b300 = 25 data bytes
PRESENCE_ZEROS = "00" * 25


# ════════════════════════════════════════════
#  PACKET BUILDERS
# ════════════════════════════════════════════

def build_login_packet(token_hex: str) -> bytes:
    """
    Build the dynamic-length login packet:
    [2-byte length][FF02][0020<token>0000]
    """
    token_with_prefix = "0020" + token_hex + "0000"
    raw_token = binascii.unhexlify(token_with_prefix)
    payload = b"\xFF\x02" + raw_token
    return len(payload).to_bytes(2, "big") + payload


def build_attack_packet(target_uid: str) -> str:
    """Build attack hex string: 000a0241 + <uid> + 00000001"""
    return PKT_ATTACK_PREFIX + target_uid + "00000001"


def build_coord_packet(coords: str) -> str:
    """Build coordinate heartbeat: 00060101 + <4-byte coords>"""
    return PKT_COORD_PREFIX + coords


def build_map_data_packet(map_hex: str, x: str, y: str) -> str:
    """
    Build map position packet for world entry:
    000e01100000<map_2byte>0000<x_2byte>0000<y_2byte>
    Length 000e = 14 bytes payload
    """
    return f"000e01100000{map_hex}0000{x}0000{y}"


def build_bulk_data_packet(map_hex: str) -> str:
    """Build bulk action data with current map reference."""
    return f"1100000000000000000000{map_hex}00023209"


def build_warp_exit_packet(portal_id: str, current_map: str) -> str:
    """3002 EXIT packet for leaving current map."""
    return f"000f300211000000{portal_id.zfill(2)}000000000000{current_map}"


def build_warp_position_packet(target_map: str, x: str, y: str) -> str:
    """110 POSITION packet for warp destination."""
    return f"000e01100000{target_map}0000{x}0000{y}"


def build_warp_entry_packet(target_map: str) -> str:
    """3002 ENTRY packet for arriving at new map."""
    return f"000f30021100000000000000000000{target_map}"


def build_world_ticks_packet() -> str:
    """Presence/world ticks packet: 001bb300 + 25 zero bytes (total 29 bytes)."""
    return PKT_PRESENCE_START + PRESENCE_ZEROS
