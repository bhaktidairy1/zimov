import tkinter as tk
from tkinter import ttk
from core.game_state import state
from core.packet_helpers import hex_send
import sys

# Custom widget output redirector
class RedirectText(object):
    def __init__(self, text_widget, original_stdout):
        self.output = text_widget
        self.original_stdout = original_stdout

    def write(self, string):
        # 1. Output to VS Code terminal natively
        self.original_stdout.write(string)
        try:
            self.original_stdout.flush()
        except: pass

        # 2. Output to UI Text widget
        # Only auto-scroll if we are currently at the bottom (1.0)
        at_bottom = self.output.yview()[1] == 1.0
        self.output.insert(tk.END, string)
        if at_bottom:
            self.output.see(tk.END)

    def flush(self):
        try:
            self.original_stdout.flush()
        except: pass

class GameView(ttk.Frame):
    def __init__(self, parent, client_instance):
        super().__init__(parent)
        self.pack(fill="both", expand=True, padx=10, pady=10)
        self.client = client_instance

        # --- Top frame (Mode + Pause) ---
        top_frame = ttk.Frame(self)
        top_frame.pack(fill="x", pady=5)
        
        mode_lf = ttk.LabelFrame(top_frame, text="System Mode")
        mode_lf.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        self.mode_var = tk.StringVar(value="STANDBY")
        ttk.Radiobutton(mode_lf, text="Standby", variable=self.mode_var, value="STANDBY", command=self.update_mode).pack(side="left", padx=5, pady=5)
        ttk.Radiobutton(mode_lf, text="Auto-Colon", variable=self.mode_var, value="AUTO", command=self.update_mode).pack(side="left", padx=5, pady=5)
        ttk.Radiobutton(mode_lf, text="Manual", variable=self.mode_var, value="MANUAL", command=self.update_mode).pack(side="left", padx=5, pady=5)

        pause_frame = ttk.Frame(top_frame)
        pause_frame.pack(side="right")
        self.pause_btn_text = tk.StringVar(value="PAUSE COORDS")
        self.pause_btn = ttk.Button(pause_frame, textvariable=self.pause_btn_text, command=self.toggle_pause)
        self.pause_btn.pack(side="right", padx=5, pady=5)

        # --- Middle frame (Hex Injector + Radar) ---
        mid_frame = ttk.Frame(self)
        mid_frame.pack(fill="x", pady=5)
        
        hex_lf = ttk.LabelFrame(mid_frame, text="Custom Hex Injector")
        hex_lf.pack(fill="x", pady=5)
        self.hex_entry = ttk.Entry(hex_lf)
        self.hex_entry.pack(side="left", fill="x", expand=True, padx=5, pady=5)
        ttk.Button(hex_lf, text="Send Hex", command=self.send_custom_hex).pack(side="right", padx=5, pady=5)

        radar_lf = ttk.LabelFrame(self, text="Radar")
        radar_lf.pack(fill="both", expand=True, pady=5)
        self.monster_lb = tk.Listbox(radar_lf, height=6)
        self.monster_lb.pack(fill="both", expand=True, padx=5, pady=5)
        self.monster_lb.bind('<<ListboxSelect>>', self.on_select_monster)

        # --- Bottom frame (Debug Terminal) ---
        log_lf = ttk.LabelFrame(self, text="Application Logs (Debug Terminal)")
        log_lf.pack(fill="both", expand=True, pady=5)
        
        # We use standard tk.Text for text area but we'll add a scrollbar
        text_container = ttk.Frame(log_lf)
        text_container.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.text_area = tk.Text(text_container, height=12, bg="#1e1e1e", fg="#d4d4d4", font=("Consolas", 9), wrap="word")
        self.text_area.pack(side="left", fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(text_container, command=self.text_area.yview)
        scrollbar.pack(side="right", fill="y")
        self.text_area.config(yscrollcommand=scrollbar.set)
        
        # Hijack sys.stdout to output to text area AND original console!
        if not isinstance(sys.stdout, RedirectText):
            sys.stdout = RedirectText(self.text_area, sys.stdout)

        self.refresh_ui()

    def toggle_pause(self):
        state.paused = not state.paused
        if state.paused:
            self.pause_btn_text.set("RESUME COORDS")
        else:
            self.pause_btn_text.set("PAUSE COORDS")

    def send_custom_hex(self):
        raw = self.hex_entry.get().strip()
        if not raw: return
        try:
            if all(c in "0123456789abcdefABCDEF " for c in raw) and (len(raw.replace(" ","")) % 2 == 0):
                hex_send(self.client.sock, raw, "MANUAL INJECT")
                self.hex_entry.delete(0, tk.END)
        except Exception as e:
            print(f"[Error injecting] {e}")
    
    def update_mode(self):
        state.mode = self.mode_var.get()
        print(f"[*] State mode updated: {state.mode}")

    def on_select_monster(self, event):
        if state.mode != "MANUAL": return
        selection = self.monster_lb.curselection()
        if selection:
            text = self.monster_lb.get(selection[0])
            uid = text.split("UID: ")[1].split(" ")[0]
            state.target_uid = uid

    def refresh_ui(self):
        # We only want to delete and redraw if we really have to visually keep list fresh
        yview = self.monster_lb.yview()
        
        self.monster_lb.delete(0, tk.END)
        for i, (uid, data) in enumerate(list(state.monsters.items())):
            name = "Colon" if data['id'] <= 2 else f"Mob({data['id']})"
            active = " [TARGET]" if uid == state.target_uid else ""
            self.monster_lb.insert(tk.END, f"{name} | UID: {uid}{active}")
            
            # Re-apply selection state intuitively
            if uid == state.target_uid:
                self.monster_lb.selection_set(i)
                
        # Restore scroll view
        if self.monster_lb.size() > 0:
            self.monster_lb.yview_moveto(yview[0])
            
        self.after(1000, self.refresh_ui)
