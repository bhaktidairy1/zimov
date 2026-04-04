import tkinter as tk
from tkinter import ttk
import threading

class LoginView(ttk.Frame):
    def __init__(self, parent, client_instance, on_success_callback):
        super().__init__(parent)
        self.pack(fill="both", expand=True)
        self.client = client_instance
        self.on_success = on_success_callback

        ttk.Label(self, text="Iruna Commander", font=("Segoe UI", 24, "bold")).pack(pady=(60, 20))
        
        self.url_var = tk.StringVar()
        self.url_var.set("https://gae4php82-real.an.r.appspot.com/_ah/login?continue=https://gae4php82-real.an.r.appspot.com/authcreate&auth=g.a0008AjsE7nmtOE_FRrLzq3c0eCenIrHPLtvizyyNSyUpEC01rs3xOPaAL3b6yqU6aCo6AzWVQACgYKAesSARESFQHGX2MivSa5uCui6fUjbNajHhfgERoVAUF8yKoQVfPkaFGTvdLOGFA-XYpY0076")
        
        ttk.Label(self, text="Mage Login URL:").pack(pady=(10, 0))
        url_entry = ttk.Entry(self, textvariable=self.url_var, width=80)
        url_entry.pack(pady=5, padx=20)
        
        # 'Accent.TButton' is from Sun-Valley theme for styled buttons
        self.login_btn = ttk.Button(self, text="CONNECT", style="Accent.TButton", command=self.do_login)
        self.login_btn.pack(pady=30)
        
        self.status = tk.StringVar()
        ttk.Label(self, textvariable=self.status).pack(pady=10)

    def do_login(self):
        url = self.url_var.get().strip()
        if not url: return
        self.login_btn.config(state="disabled")
        self.status.set("Connecting... Check Command Output (if launched via terminal)")
        
        def run():
            success = self.client.connect_and_start(url)
            if success:
                self.after(0, self.on_success)
            else:
                self.after(0, lambda: self.status.set("Connection failed! Check Logs."))
                self.after(0, lambda: self.login_btn.config(state="normal"))
                
        threading.Thread(target=run, daemon=True).start()
