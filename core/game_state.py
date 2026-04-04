import threading

class GameState:
    def __init__(self):
        self.stop_event = threading.Event()
        self.monsters = {}         
        self.target_uid = None     
        self.mode = "STANDBY"      
        self.last_map_coords = "82005a00" 
        self.waiting_for_hit = threading.Event()
        self.char_id_hex = ""
        self.damage_log = []
        self.paused = False

state = GameState()
