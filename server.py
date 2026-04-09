import sys
import threading
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from core.client import client
from core.game_state import state

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

@app.route("/")
def index():
    return send_from_directory("web", "index.html")

@app.route("/<path:path>")
def static_files(path):
    return send_from_directory("web", path)

@app.route("/api/connect", methods=["POST"])
def connect_iruna():
    data = request.json
    url = data.get("url")
    if not url: return jsonify({"error": "No URL provided"}), 400

    def background_connect():
        client.connect_and_start(url)

    threading.Thread(target=background_connect, daemon=True).start()
    return jsonify({"status": "Connecting..."})

@app.route("/api/state", methods=["GET"])
def get_state():
    return jsonify({
        "connected": client.is_connected,
        "mode": state.mode,
        "paused": state.paused,
        "targetUid": state.target_uid,
        "monsters": state.monsters
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
        
    return jsonify({"error": "Unknown action"}), 400

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
