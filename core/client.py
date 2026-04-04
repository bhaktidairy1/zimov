import socket
import threading
import time
import binascii
import requests
from urllib.parse import urlparse
import traceback

from core.game_state import state
from core.packet_helpers import hex_recv, hex_send

HOST = "202.239.51.41"
PORT = 30001

class IrunaClient:
    def __init__(self):
        self.sock = None
        self.login_token_hex = None
        self.char_id_hex = None
        self.is_connected = False

    def fetch_token(self, mageurl):
        print(f"[+] Fetching auth token for {mageurl[:40]}...")
        session = requests.Session()
        session.get(mageurl, allow_redirects=True)
        base = f"{urlparse(mageurl).scheme}://{urlparse(mageurl).netloc}"
        resp = session.get(f"{base}/authcreate")
        login_token = resp.text.strip()
        self.login_token_hex = login_token.encode().hex()
        print("[+] Token:", self.login_token_hex)

    def connect_and_start(self, mageurl):
        try:
            self.fetch_token(mageurl)
        except Exception as e:
            print(f"[-] Failed to fetch token: {e}")
            return False

        try:
            token_with_prefix = "0020" + self.login_token_hex + "0000"
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(5.0)
            print(f"[+] Connecting to {HOST}:{PORT} …")
            self.sock.connect((HOST, PORT))
            print("[+] Connected.\n")

            # Init Sequence
            hex_send(self.sock, "0002fff3", "Init Packet")
            hex_recv(self.sock, label="Init Header")

            raw_token = binascii.unhexlify(token_with_prefix)
            payload = b"\xFF\x02" + raw_token
            login_packet = len(payload).to_bytes(2, "big") + payload
            self.sock.sendall(login_packet)
            print(f"→ Login Packet: {binascii.hexlify(login_packet).decode()}")

            data = hex_recv(self.sock, label="Login ACK")
            h = binascii.hexlify(data).decode()
            if not h.startswith("00000003ff0200"):
                print("[-] Unexpected login response:", h)
                self.sock.close()
                return False
            print("[+] Login OK.\n")

            try:
                self.sock.settimeout(0.3)
                extra = hex_recv(self.sock, label="ff03 + char info")
                hexed = binascii.hexlify(extra).decode()
                idx = hexed.find("ff030100000001")
                if idx != -1 and len(hexed) >= idx + 14 + 8:
                    self.char_id_hex = hexed[idx + 14 : idx + 14 + 8]
                    print(f"[+] Parsed char_id_hex: {self.char_id_hex}\n")
                else:
                    print("[-] Couldn't locate char_id_hex.")
                    self.sock.close()
                    return False
            except socket.timeout:
                print("[-] Timeout waiting for ff03.")
                self.sock.close()
                return False
            finally:
                self.sock.settimeout(5.0)

            # Replay Sequence
            def send_and_log(pkt_hex, label=None, delay=0.1):
                hex_send(self.sock, pkt_hex, label=label)
                time.sleep(delay)

            send_and_log("0002f032", "Character Select")
            hex_recv(self.sock, label="Character Info")

            send_and_log("00060001", "Enter World")
            send_and_log(self.char_id_hex, "Character ID")
            hex_recv(self.sock, label="Character Info")

            send_and_log("000623f3", "Post-Map")
            send_and_log(self.char_id_hex, "Character ID Repeat")
            hex_recv(self.sock, label="Character Info")

            for step in ["00023300", "00023303", "00023300", "00023303"]:
                send_and_log(step, "Movement Step")
            hex_recv(self.sock, label="Pre-Movement Sync")

            send_and_log("00026002", "Movement Step")
            hex_recv(self.sock, label="Movement Sync")

            send_and_log("001bb300", "Presence Start")
            send_and_log("00000000000000000000000000000000000000000000000000", "Zeroes")

            send_and_log("0002013a", "Map Location Begin")
            send_and_log("000e01100000012c0000470000001000", "Map Data")  
            hex_recv(self.sock, label="Ack for Position")

            send_and_log("0002013a", "Resend Position")
            hex_recv(self.sock, label="Extra State Data")

            send_and_log("000f3002", "Bulk Action")
            send_and_log("1100000000000000000000012c00023209", "Bulk Action Contd.")

            send_and_log("0002016000028100000281100002830000028200", "Trigger Motion")
            hex_recv(self.sock, label="Motion Ack")

            send_and_log("0003840400", "Visuals Setup")
            send_and_log("00025003", "World Ticks Start")
            send_and_log("001bb30000000000000000000000000000000000000000000000000000", "World Ticks")

            hex_recv(self.sock, label="Server Update")

            print("\n[+] Game session established. Starting threads...")
            self.is_connected = True
            threading.Thread(target=self.coordinate_sender, daemon=True).start()
            threading.Thread(target=self.continuous_receiver, daemon=True).start()
            threading.Thread(target=self.combat_engine, daemon=True).start()

            return True

        except Exception as e:
            print(f"[CRITICAL] Network Error: {e}")
            self.is_connected = False
            return False

    def coordinate_sender(self):
        while not state.stop_event.is_set():
            if state.paused:
                time.sleep(0.5)
                continue
            try:
                current_pos = state.last_map_coords
                if state.target_uid and state.target_uid in state.monsters:
                    m = state.monsters[state.target_uid]
                    current_pos = m['x'] + m['y']
                hex_send(self.sock, "00060101" + current_pos)
            except: break
            time.sleep(1.0)
            
    def combat_engine(self):
        while not state.stop_event.is_set():
            if state.mode == "STANDBY":
                state.target_uid = None
                time.sleep(0.5)
                continue
            if state.target_uid and state.target_uid in state.monsters:
                attack_pkt = "000a0241" + state.target_uid + "00000001"
                state.waiting_for_hit.clear()
                hex_send(self.sock, attack_pkt)
                state.waiting_for_hit.wait(timeout=0.8)
                time.sleep(0.4) 
            elif state.mode == "AUTO":
                for uid, data in state.monsters.items():
                    if data['id'] in [0, 1, 2]:
                        state.target_uid = uid
                        break
                time.sleep(0.2)
            else:
                time.sleep(0.5)

    def continuous_receiver(self):
        buffer = b""
        print("[*] Receiver Thread: Online and Listening...")
        while not state.stop_event.is_set():
            try:
                data = self.sock.recv(4096)
                if not data: 
                    print("\n[!!!] SERVER DISCONNECTED")
                    break
                buffer += data
                while len(buffer) >= 6:
                    pkt_len = int.from_bytes(buffer[0:4], "big")
                    opcode = int.from_bytes(buffer[4:6], "big")
                    total_pkt_size = pkt_len + 4
                    if pkt_len > 10000 or pkt_len == 0:
                        buffer = buffer[1:] 
                        continue
                    if len(buffer) < total_pkt_size: break 
                    
                    raw_packet = buffer[:total_pkt_size]
                    payload = buffer[6:total_pkt_size]
                    
                    # Instead of ignoring everything, print the hex for standard debugging
                    # Log EVERYTHING just like old script
                    opcode_hex = hex(opcode)
                    print(f"← [RECV] {opcode_hex} | {binascii.hexlify(raw_packet).decode()}")
                    
                    if opcode == 0xb503:
                        try:
                            raw_map = binascii.hexlify(payload[3:5]).decode()
                            raw_x = int.from_bytes(payload[7:9], "big")
                            raw_y = int.from_bytes(payload[11:13], "big")
                            shifted_x = format((raw_x << 8) & 0xFFFF, '04x')
                            shifted_y = format((raw_y << 8) & 0xFFFF, '04x')
                            state.last_map_coords = shifted_x + shifted_y
                            print(f"\n[!] AUTO-SYNC: Map {raw_map} | Coords {shifted_x}{shifted_y}")
                        except: pass
                    if opcode == 0x245:
                        uid = binascii.hexlify(payload[0:4]).decode()
                        m_id = int.from_bytes(payload[4:6], "big")
                        state.monsters[uid] = {
                            'id': m_id, 
                            'x': binascii.hexlify(payload[6:7]).decode() + "00", 
                            'y': binascii.hexlify(payload[8:9]).decode() + "00"
                        }
                    buffer = buffer[total_pkt_size:]
            except socket.timeout: continue
            except Exception as e:
                print(f"[CRITICAL] Error in receiver: {e}")
                break
        
        print("[*] Receiver Thread: Offline.")

client = IrunaClient()
