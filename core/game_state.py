import threading

class GameState:
    def __init__(self):
        self.stop_event = threading.Event()
        self.monsters = {}         
        self.target_uid = None     
        self.mode = "STANDBY"      
        self.last_map_coords = "47001000"  # Miscerene Plains spawn (x=0x47, y=0x10)
        self.waiting_for_hit = threading.Event()
        self.char_id_hex = ""
        self.damage_log = []
        self.paused = False
        self.inventory = {}
        self.current_map_hex = "012c"  # Default: Miscerene Plains (map 300)
        self.map_name = "Miscerene Plains"
        self.teleport_event = threading.Event()
        self.teleport_success = False
        self.map_ready_event = threading.Event()
        self.map_data_event = threading.Event()
        self.check_alive_event = threading.Event()

        # Scripting & Boss Automation
        self.in_scripted_sequence = False
        self.auto_zimov_running = False
        self.auto_zimov_kill_count = 0
        self.auto_zimov_run_count = 0
        self.spina_earned = 0
        self.pet_uid_hex = None
        self.boss_id_hex = None
        self.boss_spawn_event = threading.Event()
        self.boss_death_event = threading.Event()

state = GameState()
