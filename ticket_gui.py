import json
import os
import io
import time
import zipfile
import shutil
import tkinter as tk
from tkinter import messagebox

import requests

BG_COLOR = "#000000"
FG_COLOR = "#00FF00"

DATA_FILE = "ids.json"
SERVER_URL = os.environ.get("SYNC_SERVER", "https://localhost:1981")
CERT_FILE = "server.crt"

SESSION = requests.Session()
SESSION.verify = CERT_FILE if os.path.exists(CERT_FILE) else True

# Mapping main IDs to sets of alt IDs
ALT_DATABASE = {}

# Mapping every known ID to its userRank
RANKS = {}


class ToolTip:
    """Simple tooltip that appears when hovering over a widget."""

    def __init__(self, widget, text=""):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, event=None):
        if self.tipwindow or not self.text:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 10
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.configure(bg=BG_COLOR)
        label = tk.Label(
            tw,
            text=self.text,
            bg=BG_COLOR,
            fg=FG_COLOR,
            justify=tk.LEFT,
            relief=tk.SOLID,
            borderwidth=1,
        )
        label.pack(ipadx=1)
        tw.wm_geometry(f"+{x}+{y}")

    def hide(self, event=None):
        tw = self.tipwindow
        if tw:
            tw.destroy()
            self.tipwindow = None

def load_data():
    """Load ID data from disk if available."""
    global ALT_DATABASE, RANKS
    if not os.path.exists(DATA_FILE):
        return
    with open(DATA_FILE, "r") as f:
        data = json.load(f)
    ALT_DATABASE = {k: set(v) for k, v in data.get("ALT_DATABASE", {}).items()}
    RANKS = data.get("RANKS", {})


def save_data():
    """Persist ID data to disk."""
    data = {
        "ALT_DATABASE": {k: sorted(v) for k, v in ALT_DATABASE.items()},
        "RANKS": RANKS,
    }
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def id_exists(identifier):
    """Return True if the identifier is already stored as a main or alt ID."""
    return identifier in RANKS


def find_main_id(identifier):
    """Given any ID, return its main ID if found."""
    if identifier in ALT_DATABASE:
        return identifier
    for main, alts in ALT_DATABASE.items():
        if identifier in alts:
            return main
    return None


def ask_alts(main_id):
    """Ask user to add alt IDs after submitting main ID."""
    if messagebox.askyesno("Add Alts", "Add any alts?"):
        alt_window = tk.Toplevel()
        alt_window.title("Alt IDs")
        alt_window.configure(bg=BG_COLOR)

        tk.Label(
            alt_window,
            text="Enter Alt IDs (comma separated):",
            bg=BG_COLOR,
            fg=FG_COLOR,
        ).pack(padx=10, pady=10)
        alt_entry = tk.Entry(
            alt_window, width=40, bg=BG_COLOR, fg=FG_COLOR, insertbackground=FG_COLOR
        )
        alt_entry.pack(padx=10, pady=(0, 10))

        def submit_alts():
            raw_alts = [a.strip() for a in alt_entry.get().split(",") if a.strip()]
            seen = set()
            for alt in raw_alts:
                if alt == main_id or alt in seen or id_exists(alt):
                    messagebox.showerror("Duplicate ID", f"Alt ID {alt} already exists.")
                    return
                seen.add(alt)
            for alt in raw_alts:
                RANKS[alt] = "ALT"
            ALT_DATABASE[main_id].update(raw_alts)
            save_data()
            update_stats()
            alts_display = ", ".join(raw_alts) if raw_alts else "None"
            messagebox.showinfo("Submitted", f"Main ID: {main_id}\nAlts: {alts_display}")
            alt_window.destroy()

        tk.Button(
            alt_window,
            text="Submit",
            command=submit_alts,
            bg=BG_COLOR,
            fg=FG_COLOR,
            activebackground=BG_COLOR,
            activeforeground=FG_COLOR,
            highlightbackground=FG_COLOR,
        ).pack(pady=(0, 10))
    else:
        messagebox.showinfo("Submitted", f"Main ID: {main_id}")


def send_id(event=None):
    main_id = entry.get().strip()
    if not main_id:
        messagebox.showwarning("Input Error", "Please enter your main ID.")
        return
    if id_exists(main_id):
        messagebox.showerror("Duplicate ID", f"ID {main_id} already exists.")
        entry.delete(0, tk.END)
        return
    ALT_DATABASE[main_id] = set()
    RANKS[main_id] = "USER"
    save_data()
    update_stats()
    ask_alts(main_id)
    entry.delete(0, tk.END)


def load_alts():
    """Load associated IDs for the given main or alt ID."""
    identifier = entry.get().strip()
    if not identifier:
        messagebox.showwarning("Input Error", "Please enter an ID.")
        return

    main_id = find_main_id(identifier)
    if not main_id:
        messagebox.showinfo("Alt IDs", f"No records found for ID: {identifier}")
        return

    alts = ALT_DATABASE.get(main_id, set())
    alt_window = tk.Toplevel()
    alt_window.title(f"Accounts for {main_id}")
    alt_window.configure(bg=BG_COLOR)

    tk.Label(alt_window, text=f"Main ID: {main_id}", bg=BG_COLOR, fg=FG_COLOR).pack(
        padx=10, pady=10
    )
    listbox = tk.Listbox(alt_window, width=40, bg=BG_COLOR, fg=FG_COLOR)
    listbox.insert(tk.END, f"Main (USER): {main_id}")
    for alt in sorted(alts):
        listbox.insert(tk.END, f"Alt (ALT): {alt}")
    listbox.pack(padx=10, pady=(0, 10))


def update_stats():
    mains = len(ALT_DATABASE)
    alts = sum(len(alts) for alts in ALT_DATABASE.values())
    stats_label.config(text=f"Mains: {mains}\nAlts: {alts}")


def _zip_repository():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for root_dir, dirs, files in os.walk("."):
            dirs[:] = [d for d in dirs if d not in {".git", "__pycache__", "server_data"}]
            for file in files:
                path = os.path.join(root_dir, file)
                arcname = os.path.relpath(path, ".")
                zf.write(path, arcname)
    buffer.seek(0)
    return buffer.getvalue()


def backup_to_server():
    try:
        data = _zip_repository()
        SESSION.post(
            f"{SERVER_URL}/upload", files={"file": ("backup.zip", data)}, timeout=15
        ).raise_for_status()
        messagebox.showinfo("Backup", "Backup completed successfully.")
    except Exception as exc:
        messagebox.showerror("Backup Failed", str(exc))


def load_from_server():
    try:
        resp = SESSION.get(f"{SERVER_URL}/download", timeout=15)
        resp.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                dest = info.filename
                server_mtime = time.mktime(info.date_time + (0, 0, -1))
                if os.path.exists(dest) and os.path.getmtime(dest) >= server_mtime:
                    continue
                os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
                with zf.open(info) as src, open(dest, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                os.utime(dest, (server_mtime, server_mtime))
        messagebox.showinfo("Restore", "Backup loaded from server.")
    except Exception as exc:
        messagebox.showerror("Restore Failed", str(exc))


def on_close():
    """Backup to server before closing the application."""
    backup_to_server()
    root.destroy()


def make_command():
    """Generate a batch file with MongoDB commands to set userRank."""
    if not RANKS:
        messagebox.showwarning("No IDs", "No IDs available to generate commands.")
        return
    lines = ["@echo off"]
    for identifier, rank in sorted(RANKS.items()):
        lines.append(
            f"mongo supergo2 --eval \"db.game_account.updateOne({{id: '{identifier}'}}, {{$set: {{userRank: '{rank}'}}}})\""
        )
    with open("set_user_ranks.bat", "w") as f:
        f.write("\n".join(lines))
    messagebox.showinfo("Command Created", "set_user_ranks.bat has been generated.")


def make_champ_points_command(amount):
    """Return a function that writes a batch file to add champion points."""

    def command():
        lines = ["@echo off"]
        lines.append(
            f"mongo supergo2 --eval \"db.game_users.updateMany({{}}, {{$inc: {{'game_resources.championPoints': {amount}}}}})\""
        )
        filename = f"add_{amount}_champion_points.bat"
        with open(filename, "w") as f:
            f.write("\n".join(lines))
        messagebox.showinfo("Command Created", f"{filename} has been generated.")

    return command


# Map command names to their functions
COMMANDS = {
    "Set User Ranks": make_command,
    "Add 100 Champion Points": make_champ_points_command(100),
    "Add 200 Champion Points": make_champ_points_command(200),
    "Add 500 Champion Points": make_champ_points_command(500),
    "Add 1000 Champion Points": make_champ_points_command(1000),
    "Add 2500 Champion Points": make_champ_points_command(2500),
    "Add 5000 Champion Points": make_champ_points_command(5000),
    "Add 10000 Champion Points": make_champ_points_command(10000),
}


COMMAND_DESCRIPTIONS = {
    "Set User Ranks": "Generate commands to set userRank for each stored ID.",
    "Add 100 Champion Points": "Add 100 championPoints to every user.",
    "Add 200 Champion Points": "Add 200 championPoints to every user.",
    "Add 500 Champion Points": "Add 500 championPoints to every user.",
    "Add 1000 Champion Points": "Add 1000 championPoints to every user.",
    "Add 2500 Champion Points": "Add 2500 championPoints to every user.",
    "Add 5000 Champion Points": "Add 5000 championPoints to every user.",
    "Add 10000 Champion Points": "Add 10000 championPoints to every user.",
}


def build_command():
    """Run the selected command from the dropdown."""
    COMMANDS[command_var.get()]()


root = tk.Tk()
root.title("Dark Galaxy Command Box")
root.configure(bg=BG_COLOR)

# Load any previously saved IDs
load_data()

# Auto-download latest files from server at startup
load_from_server()

title_label = tk.Label(
    root, text="Dark Galaxy Command Box", bg=BG_COLOR, fg=FG_COLOR, font=("Helvetica", 16, "bold")
)
title_label.pack(pady=(10, 0))

stats_label = tk.Label(root, bg=BG_COLOR, fg=FG_COLOR, justify="right")
stats_label.pack(anchor="ne", padx=10, pady=10)

# Entry for main ID
entry = tk.Entry(root, width=40, bg=BG_COLOR, fg=FG_COLOR, insertbackground=FG_COLOR)
entry.pack(padx=10, pady=10)
entry.focus_set()

# Send button
send_button = tk.Button(
    root,
    text="Send",
    command=send_id,
    bg=BG_COLOR,
    fg=FG_COLOR,
    activebackground=BG_COLOR,
    activeforeground=FG_COLOR,
    highlightbackground=FG_COLOR,
)
send_button.pack(padx=10, pady=(0, 10))

# Load alts button
load_button = tk.Button(
    root,
    text="Load Alts",
    command=load_alts,
    bg=BG_COLOR,
    fg=FG_COLOR,
    activebackground=BG_COLOR,
    activeforeground=FG_COLOR,
    highlightbackground=FG_COLOR,
)
load_button.pack(padx=10, pady=(0, 10))

# Commands dropdown and build button
commands_frame = tk.Frame(root, bg=BG_COLOR)
commands_frame.pack(padx=10, pady=(0, 10))

tk.Label(commands_frame, text="Commands:", bg=BG_COLOR, fg=FG_COLOR).pack(side="left")

command_var = tk.StringVar(value="Set User Ranks")
command_menu = tk.OptionMenu(commands_frame, command_var, *COMMANDS.keys())
command_menu.config(
    bg=BG_COLOR,
    fg=FG_COLOR,
    highlightbackground=FG_COLOR,
    activebackground=BG_COLOR,
    activeforeground=FG_COLOR,
)
command_menu["menu"].config(bg=BG_COLOR, fg=FG_COLOR)
command_menu.pack(side="left", padx=5)

tooltip = ToolTip(command_menu, COMMAND_DESCRIPTIONS[command_var.get()])

def _update_tooltip(*args):
    tooltip.text = COMMAND_DESCRIPTIONS[command_var.get()]


command_var.trace_add("write", _update_tooltip)

tk.Button(
    commands_frame,
    text="Build",
    command=build_command,
    bg=BG_COLOR,
    fg=FG_COLOR,
    activebackground=BG_COLOR,
    activeforeground=FG_COLOR,
    highlightbackground=FG_COLOR,
).pack(side="left", padx=5)

# Backup and restore buttons
backup_frame = tk.Frame(root, bg=BG_COLOR)
backup_frame.pack(padx=10, pady=(0, 10))

tk.Button(
    backup_frame,
    text="Backup",
    command=backup_to_server,
    bg=BG_COLOR,
    fg=FG_COLOR,
    activebackground=BG_COLOR,
    activeforeground=FG_COLOR,
    highlightbackground=FG_COLOR,
).pack(side="left", padx=5)

tk.Button(
    backup_frame,
    text="Load Backup",
    command=load_from_server,
    bg=BG_COLOR,
    fg=FG_COLOR,
    activebackground=BG_COLOR,
    activeforeground=FG_COLOR,
    highlightbackground=FG_COLOR,
).pack(side="left", padx=5)

# Bind Return key to send
root.bind("<Return>", send_id)

# Backup before closing when the window is closed
root.protocol("WM_DELETE_WINDOW", on_close)

update_stats()
root.mainloop()
