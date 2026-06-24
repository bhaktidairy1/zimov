import os
import sys
import argparse
import threading
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from core.client import client
from core.game_state import state
from core.map_teleport import teleport, teleport_preset, KNOWN_MAPS, find_map_by_name

# Parse arguments
parser = argparse.ArgumentParser(description="Iruna Server")
parser.add_argument("--minimal", action="store_true", help="Run the server with the minimal web UI")
parser.add_argument("--url", type=str, help="Launch URL to auto-connect and auto-start")
args = parser.parse_args()

app = Flask(__name__, static_folder="web")
CORS(app)

# Buffer for sys.stdout redirection
log_buffer = []

class WebLogRedirector:
    def __init__(self, original_stdout):
        self.original_stdout = original_stdout
        self.current_line = ""

    def write(self, string):
        self.original_stdout.write(string)
        self.current_line += string
        while '\n' in self.current_line:
            line, self.current_line = self.current_line.split('\n', 1)
            if len(log_buffer) > 500:
                log_buffer.pop(0)
            log_buffer.append(line + '\n')
            
    def flush(self):
        self.original_stdout.flush()

# Route stdout heavily
sys.stdout = WebLogRedirector(sys.stdout)

if args.url:
    def auto_connect_loop():
        import time
        print(f"[*] Auto-connecting to {args.url[:50]}...")
        if client.connect_and_start(args.url):
            print("[*] Connected! Waiting for world to load...")
            # Wait until we are fully loaded in a map
            while not state.current_map_hex:
                time.sleep(1)
            # Short buffer to ensure environment is stabilized
            time.sleep(2)
            
            print("[*] World loaded. Starting Auto-Zimov loop!")
            from core.boss_module import auto_zimov_loop
            # Start the loop in this thread
            auto_zimov_loop(client.sock)
            
    threading.Thread(target=auto_connect_loop, daemon=True).start()

@app.route("/")
def index():
    if args.minimal:
        return send_from_directory("web", "minimal.html")
    return send_from_directory("web", "index.html")

@app.route("/<path:path>")
def static_files(path):
    return send_from_directory("web", path)

@app.route("/api/connect", methods=["POST"])
def connect_iruna():
    data = request.json
    url = data.get("url")
    if not url: return jsonify({"error": "No URL provided"}), 400

    def auto_connect_and_start_zimov():
        import time
        print(f"[*] Auto-connecting to {url[:50]}...")
        if client.connect_and_start(url):
            if args.minimal:
                print("[*] Connected! Waiting for world to load to auto-start Zimov...")
                # Wait until we are fully loaded in a map
                while not state.current_map_hex:
                    time.sleep(1)
                # Short buffer to ensure environment is stabilized
                time.sleep(2)
                
                print("[*] World loaded. Starting Auto-Zimov loop!")
                from core.boss_module import auto_zimov_loop
                # Start the loop in this thread
                auto_zimov_loop(client.sock)

    threading.Thread(target=auto_connect_and_start_zimov, daemon=True).start()
    return jsonify({"status": "Connecting..."})

@app.route("/api/state", methods=["GET"])
def get_state():
    return jsonify({
        "connected": client.is_connected,
        "mode": state.mode,
        "paused": state.paused,
        "targetUid": state.target_uid,
        "monsters": state.monsters,
        "inventory": state.inventory,
        "map_name": state.map_name,
        "current_map_hex": state.current_map_hex,
        "auto_zimov_running": getattr(state, "auto_zimov_running", False),
        "auto_zimov_kill_count": getattr(state, "auto_zimov_kill_count", 0),
        "auto_zimov_run_count": getattr(state, "auto_zimov_run_count", 0),
        "spina_earned": getattr(state, "spina_earned", 0)
    })

@app.route("/api/logs", methods=["GET"])
def get_logs():
    global log_buffer
    logs_to_send = log_buffer[:]
    log_buffer = []  # clear after fetching to keep payload lightning fast
    return jsonify({"logs": logs_to_send})

@app.route("/api/action", methods=["POST"])
def perform_action():
    data = request.json
    action_type = data.get("type")
    
    if action_type == "set_mode":
        state.mode = data.get("mode")
        return jsonify({"success": True})
        
    elif action_type == "toggle_pause":
        state.paused = not state.paused
        return jsonify({"success": True, "paused": state.paused})
        
    elif action_type == "inject_hex":
        raw = data.get("hex", "").strip()
        try:
            if all(c in "0123456789abcdefABCDEF " for c in raw) and (len(raw.replace(" ","")) % 2 == 0):
                from core.packet_helpers import hex_send
                hex_send(client.sock, raw, "MANUAL INJECT")
                return jsonify({"success": True})
            return jsonify({"error": "Invalid hex format"}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 500
            
    elif action_type == "set_target":
        state.target_uid = data.get("uid")
        return jsonify({"success": True})

    elif action_type == "teleport":
        preset = data.get("preset")
        if preset:
            threading.Thread(
                target=teleport_preset,
                args=(client.sock, preset),
                daemon=True
            ).start()
            return jsonify({"success": True, "target": preset})
        map_id = data.get("map_id")
        if map_id:
            x = data.get("x")
            y = data.get("y")
            threading.Thread(
                target=teleport,
                args=(client.sock, int(map_id), x, y),
                daemon=True
            ).start()
            return jsonify({"success": True, "map_id": map_id})
        return jsonify({"error": "Need 'preset' or 'map_id'"}), 400

    elif action_type == "search_maps":
        query = data.get("query", "")
        results = find_map_by_name(query)[:20]
        return jsonify({"results": [{"id": r[0], "hex": f"{r[0]:04X}", "name": r[1]} for r in results]})

    elif action_type == "zimov_boss":
        from core.boss_module import zimov_battle_thread
        
        if state.current_map_hex != "3e1c":
            return jsonify({"status": "error", "message": "Must be in Dierolt (3e1c) to start Zimov"}), 400
            
        if state.in_scripted_sequence or getattr(state, "auto_zimov_running", False):
            return jsonify({"status": "error", "message": "A sequence is already running"}), 400
            
        threading.Thread(target=zimov_battle_thread, args=(client.sock,), daemon=True).start()
        return jsonify({"status": "zimov_started"})

    elif action_type == "kakeula_heal":
        from core.boss_module import kakeula_heal_thread
        
        if state.in_scripted_sequence or getattr(state, "auto_zimov_running", False):
            return jsonify({"status": "error", "message": "A sequence is already running"}), 400
            
        threading.Thread(target=kakeula_heal_thread, args=(client.sock,), daemon=True).start()
        return jsonify({"status": "heal_started"})

    elif action_type == "kakeula_sell":
        from core.boss_module import kakeula_sell_thread
        
        if state.in_scripted_sequence or getattr(state, "auto_zimov_running", False):
            return jsonify({"status": "error", "message": "A sequence is already running"}), 400
            
        threading.Thread(target=kakeula_sell_thread, args=(client.sock,), daemon=True).start()
        return jsonify({"status": "sell_started"})

    elif action_type == "start_auto_zimov":
        from core.boss_module import auto_zimov_loop
        
        if state.current_map_hex != "3e1c":
            return jsonify({"status": "error", "message": "Must be in Dierolt (3e1c) to start"}), 400
            
        if getattr(state, "auto_zimov_running", False) or state.in_scripted_sequence:
            return jsonify({"status": "error", "message": "A sequence is already running"}), 400
            
        threading.Thread(target=auto_zimov_loop, args=(client.sock,), daemon=True).start()
        return jsonify({"status": "auto_zimov_started"})
        
    elif action_type == "stop_auto_zimov":
        state.auto_zimov_running = False
        return jsonify({"status": "auto_zimov_stopped"})

    return jsonify({"error": "Unknown action"}), 400

def cleanup_and_exit():
    print("[!] Cleaning up resources...")
    state.auto_zimov_running = False
    
    if client.sock:
        try:
            client.sock.close()
        except:
            pass
            
    try:
        from core.packet_helpers import stop_packet_log
        stop_packet_log()
    except:
        pass
        
    print("[!] Resources freed. Exiting program.")
    os._exit(0)

@app.route("/api/stop", methods=["POST", "GET"])
@app.route("/stop", methods=["POST", "GET"])
def stop_server():
    print("[!] Shutdown requested via Web UI.")
    cleanup_and_exit()

if __name__ == "__main__":
    def find_free_port(start_port):
        import socket
        port = start_port
        while True:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.bind(("0.0.0.0", port))
                s.close()
                return port
            except OSError:
                port += 1
                
    base_port = int(os.environ.get("PORT", 10000))
    port = find_free_port(base_port)
    if port != base_port:
        print(f"[!] Port {base_port} is occupied. Using port {port} instead.")
        
    try:
        app.run(host="0.0.0.0", port=port, debug=False)
    except KeyboardInterrupt:
        print("\n[!] KeyboardInterrupt detected (CTRL+C).")
        cleanup_and_exit()
