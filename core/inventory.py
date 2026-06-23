"""
inventory.py — In-memory inventory management with SQL item DB lookup.

Tracks items via:
  - One-time 0120 fetch at login (parsed into state.inventory)
  - Ongoing 0123 (item drops) and 4018 (inventory updates) via receiver
  - No repeat 0120 requests — everything tracked in code after initial load

Item DB loaded from ItemMaster.sql (optional — code works without it).
"""
import os
import re
import sqlite3
import binascii

from core.game_state import state

# ════════════════════════════════════════════
#  ITEM DATABASE (from ItemMaster.sql)
# ════════════════════════════════════════════

_item_db = {}       # {item_id_int: name_str}
_item_types = {}    # {item_id_int: type_int}
_db_loaded = False


def load_item_db():
    """
    Load item names from ItemMaster.sql into memory.
    Uses sqlite3 in-memory DB to parse the SQL dump.
    Gracefully does nothing if the file doesn't exist.
    """
    global _item_db, _item_types, _db_loaded

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sql_path = os.path.join(base_dir, "ItemMaster.sql")

    if not os.path.exists(sql_path):
        print("[*] ItemMaster.sql not found — inventory will show raw IDs only")
        return

    try:
        with open(sql_path, "r", encoding="utf-8", errors="ignore") as f:
            sql_content = f.read()

        conn = sqlite3.connect(":memory:")
        conn.executescript(sql_content)
        cursor = conn.execute("SELECT ItemID, Name, Type FROM ItemMaster")
        for row in cursor.fetchall():
            _item_db[row[0]] = row[1]
            _item_types[row[0]] = row[2]
        conn.close()
        _db_loaded = True
        print(f"[+] Item DB loaded: {len(_item_db)} items from ItemMaster.sql")
    except Exception as e:
        print(f"[-] Failed to load item DB: {e}")


def get_item_name(item_id: int) -> str:
    """Get item name by decimal ID. Returns hex if not in DB."""
    return _item_db.get(item_id, f"Unknown(0x{item_id:04X})")


def is_known_item(item_id: int) -> bool:
    """Check if an item ID exists in the loaded DB."""
    if _db_loaded:
        return item_id in _item_db
    # Without DB, accept anything in typical game range
    return 1000 <= item_id <= 65000


# ════════════════════════════════════════════
#  INVENTORY TRACKING
# ════════════════════════════════════════════

def _inv_key(item_id: int) -> str:
    """Inventory dict key: 4-char uppercase hex like '28BE'."""
    return f"{item_id:04X}"


def add_item(item_id: int, count: int = 1, instance_hex: str = ""):
    """Add item(s) to the in-memory inventory."""
    key = _inv_key(item_id)
    if key not in state.inventory:
        state.inventory[key] = {
            "id": item_id,
            "name": get_item_name(item_id),
            "slots": [],
            "count": 0
        }
        
    # See if we already have this instance slot
    found_slot = False
    for slot in state.inventory[key]["slots"]:
        if slot["instance"] == instance_hex:
            slot["count"] += count
            found_slot = True
            break
            
    if not found_slot:
        state.inventory[key]["slots"].append({"instance": instance_hex, "count": count})
        
    state.inventory[key]["count"] += count


def set_item(item_id: int, count: int, instance_hex: str = ""):
    """Set exact count for an item slot (used by 4018 updates)."""
    key = _inv_key(item_id)
    if key not in state.inventory:
        state.inventory[key] = {
            "id": item_id,
            "name": get_item_name(item_id),
            "slots": [],
            "count": 0
        }
        
    count = max(count, 0)
    
    found_slot = False
    for slot in state.inventory[key]["slots"]:
        if slot["instance"] == instance_hex:
            slot["count"] = count
            found_slot = True
            break
            
    if not found_slot and count > 0:
        state.inventory[key]["slots"].append({"instance": instance_hex, "count": count})
        
    # Clean up empty slots and recalculate total
    state.inventory[key]["slots"] = [s for s in state.inventory[key]["slots"] if s["count"] > 0]
    state.inventory[key]["count"] = sum(s["count"] for s in state.inventory[key]["slots"])
    
    if state.inventory[key]["count"] <= 0:
        del state.inventory[key]


def remove_item(item_id: int, count: int = 1, instance_hex: str = ""):
    """Remove item(s) from inventory. Deletes entry if count reaches 0."""
    key = _inv_key(item_id)
    if key in state.inventory:
        # If an instance is specified, remove from that specific slot
        if instance_hex:
            for slot in state.inventory[key]["slots"]:
                if slot["instance"] == instance_hex:
                    slot["count"] -= count
                    break
        else:
            # Otherwise just subtract from total (mostly used for non-instanced logging)
            state.inventory[key]["count"] -= count
            
        # Clean up empty slots and recalculate total
        state.inventory[key]["slots"] = [s for s in state.inventory[key]["slots"] if s["count"] > 0]
        state.inventory[key]["count"] = sum(s["count"] for s in state.inventory[key]["slots"])
        
        if state.inventory[key]["count"] <= 0:
            del state.inventory[key]

def calculate_bag_usage():
    """Returns the total number of unique item slots taken up in the bag (max 50)"""
    slots_used = 0
    for item_data in state.inventory.values():
        slots_used += len(item_data.get("slots", []))
    return slots_used


# ════════════════════════════════════════════
#  PACKET PARSERS
# ════════════════════════════════════════════

def parse_inventory_response(data: bytes):
    """
    Parse the 0120 full inventory dump from the server.
    
    The raw data from hex_recv contains the full server response.
    We scan for valid item IDs (from the DB) and extract entries.
    
    Observed entry pattern near each item:
      [item_id 2B] [instance_id 4B] [count/flags 2B+]
    """
    h = binascii.hexlify(data).decode()

    # Find the 0120 opcode in the received data
    idx = h.find("0120")
    if idx == -1:
        print("[-] No 0120 opcode found in response")
        return
        
    # Check Bag ID to prevent Coin Bag from overwriting Main Bag
    try:
        bag_id = int(h[idx+12:idx+16], 16)
        if bag_id != 0:
            print(f"[*] Ignoring 0120 sync for alternate bag (ID {bag_id})")
            return
    except Exception:
        pass
        
    # Do NOT clear the inventory here! Iruna sends the main bag in multiple chunked 0120 packets 
    # (e.g. 15 items per packet). If we clear it here, the chunks overwrite each other!
    # state.inventory.clear()
        
    # Skip past: 0120 (4 chars) + count (8 chars) + bag ID (4 chars)
    scan_start = idx + 4 + 8 + 4
    payload_hex = h[scan_start:]

    items_found = 0
    i = 0
    while i < len(payload_hex) - 15:
        # Read 2 bytes as potential item ID
        try:
            potential_id = int(payload_hex[i:i+4], 16)
        except ValueError:
            i += 2
            continue

        if potential_id > 0 and is_known_item(potential_id):
            # Read 4-byte instance ID
            inst = payload_hex[i+4:i+12]
            # Read 2-byte count
            try:
                raw_count = int(payload_hex[i+12:i+16], 16)
            except (ValueError, IndexError):
                raw_count = 1

            count = raw_count if 0 < raw_count <= 9999 else 1

            key = _inv_key(potential_id)
            if key not in state.inventory:
                state.inventory[key] = {
                    "id": potential_id,
                    "name": get_item_name(potential_id),
                    "slots": [],
                    "count": 0
                }
            
            # Check if this slot instance already exists
            found = False
            for slot in state.inventory[key]["slots"]:
                if slot["instance"] == inst:
                    slot["count"] = count
                    found = True
                    break
                    
            if not found:
                state.inventory[key]["slots"].append({"instance": inst, "count": count})
                items_found += 1
                
            state.inventory[key]["count"] = sum(s["count"] for s in state.inventory[key]["slots"])

            # Skip past this entry (min 8 bytes = 16 hex chars)
            i += 16
            # Skip residual entry data (flags/padding) until next valid item or limit
            skipped = 0
            while i + skipped < len(payload_hex) - 4 and skipped < 12:
                try:
                    nxt = int(payload_hex[i+skipped:i+skipped+4], 16)
                except ValueError:
                    break
                if nxt > 0 and is_known_item(nxt):
                    break
                skipped += 2
            i += skipped
        else:
            i += 2

    print(f"\n[+] Inventory loaded: {items_found} unique items")
    for key, item in state.inventory.items():
        try:
            print(f"    [{key}] {item['name']} x{item['count']}")
        except UnicodeEncodeError:
            print(f"    [{key}] (name has special chars) x{item['count']}")
    print()


def handle_item_drop(payload: bytes):
    """
    Opcode 0x0123 — Item received (drop / quest reward).
    
    Payload layout (observed):
      [0:2]  padding/slot
      [2:4]  item_id (2 bytes, big-endian)
      [4:8]  instance_id (4 bytes)
      [8:10] running total or extra data
    """
    if len(payload) < 8:
        return

    item_id = int.from_bytes(payload[2:4], "big")
    instance_hex = binascii.hexlify(payload[4:8]).decode()

    name = get_item_name(item_id)
    # We do NOT add_item here to avoid double-counting.
    # The actual state update happens in the subsequent 4018 packet.
    print(f"\n[+] ITEM DROP: {name} (0x{item_id:04X})")


def handle_pet_item_drop(payload: bytes):
    """
    Opcode 0xa108 — Pet Item drop/pickup notification.
    Layout: [Length (4 bytes)] a108 [0000] [ItemID (2 bytes)] ...
    Since payload strips header and opcode, item ID is at [2:4].
    """
    if len(payload) < 6:
        return
        
    item_id = int.from_bytes(payload[2:4], "big")
    if item_id == 0: return
    
    # Pet drops go directly to the main bag, but the server skips sending 
    # a 4018 update packet for them. We manually increment here.
    add_item(item_id, count=1, instance_hex="")
    
    name = get_item_name(item_id)
    key = _inv_key(item_id)
    total = state.inventory[key]["count"]
    
    print(f"\n[+] PET ITEM DROP: {name} (0x{item_id:04X}) | total: {total} ({calculate_bag_usage()}/50 slots)")


def handle_inventory_update(payload: bytes):
    """
    Opcode 0x4018 — Inventory slot updated by server.
    
    Payload layout (observed from battle data):
      [0:4]  action type (00000001 = add/set)
      [4:6]  slot / padding
      [6:8]  item_id (2 bytes, big-endian)
      [8]    delta (1 byte, e.g. 01 for +1)
      [9:11] padding
    """
    if len(payload) < 9:
        return

    item_id = int.from_bytes(payload[6:8], "big")
    if item_id == 0:
        return

    # Parse as signed 8-bit integer for the delta
    delta = int.from_bytes(payload[8:9], byteorder="big", signed=True) if len(payload) > 8 else 1

    # The 4018 update applies to the slot that was just dropped, but we don't
    # have the exact instance hex here easily unless we parse it from previous 0123s.
    # But since delta > 0 usually just means a count goes up, we just log it.
    if delta > 0:
        # Fallback to empty instance if not tracking specifics correctly here
        add_item(item_id, count=delta, instance_hex="")
    elif delta < 0:
        remove_item(item_id, count=abs(delta))

    name = get_item_name(item_id)
    key = _inv_key(item_id)
    if key in state.inventory:
        total = state.inventory[key]["count"]
        print(f"[+] INV UPDATE: {name} (0x{item_id:04X}) | delta: {delta:+} => total: {total} ({calculate_bag_usage()}/50 slots)")
    else:
        print(f"[+] INV UPDATE: {name} (0x{item_id:04X}) | delta: {delta:+} => removed from bag")


def handle_full_inventory(payload: bytes):
    """
    Opcode 0x0120 — Full inventory response.
    Wraps payload back into a parseable format for parse_inventory_response.
    When received by the receiver thread (not during login), parse it directly.
    """
    # Reconstruct the raw data with the opcode prefix for the scanner
    fake_header = b'\x01\x20'
    parse_inventory_response(fake_header + payload)
