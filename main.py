import sys
import tkinter as tk
import sv_ttk
from ui.login_view import LoginView
from ui.game_view import GameView
from core.client import client

class RootApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Iruna Commander")
        self.root.geometry("800x750")

        # Load sun-valley theme via pip package
        try:
            sv_ttk.set_theme("dark")
        except Exception as e:
            print(f"Error loading theme: {e}")

        # Initially show login
        self.show_login()

    def show_login(self):
        self.login_view = LoginView(self.root, client, self.show_game)

    def show_game(self):
        # By the time this is called, client is authenticated successfully
        self.login_view.destroy()
        self.game_view = GameView(self.root, client)
        print("[+] Transitioned to Main Engine GUI!")
        print("\n".join(["[INFO] Output successfully redirected to GUI terminal!"] * 2))

if __name__ == "__main__":
    root = tk.Tk()
    app = RootApp(root)
    
    # Ensures cleanly closing background threads if app is closed
    def on_close():
        client.is_connected = False
        import sys
        sys.exit(0)
        
    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()
