import io
import logging
import os
import time
import zipfile
import shutil
import threading
import tkinter as tk
import hashlib
import yaml
from pathlib import Path
from flask import Flask, request, send_file

CONFIG_FILE = "config.yml"
CONFIG = {}
if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE) as f:
        CONFIG = yaml.safe_load(f) or {}

app = Flask(__name__)
DATA_DIR = Path("server_data")
DATA_DIR.mkdir(exist_ok=True)
HOST = CONFIG.get("server", {}).get("host", "0.0.0.0")
PORT = CONFIG.get("server", {}).get("port", 1981)
CERT_FILE = CONFIG.get("server", {}).get("cert", "server.crt")
KEY_FILE = CONFIG.get("server", {}).get("key", "server.key")
error_flag = False
last_hash = None
last_generated = None
status_color = "green"


def _safe_path(base: Path, target: str) -> Path:
    resolved = (base / target).resolve()
    if not str(resolved).startswith(str(base.resolve())):
        raise ValueError("Illegal path")
    return resolved


def save_zip(content: bytes):
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            dest = _safe_path(DATA_DIR, info.filename)
            dest.parent.mkdir(parents=True, exist_ok=True)
            uploaded_mtime = time.mktime(info.date_time + (0, 0, -1))
            if dest.exists() and dest.stat().st_mtime >= uploaded_mtime:
                continue
            with zf.open(info) as src, dest.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            os.utime(dest, (uploaded_mtime, uploaded_mtime))


@app.post("/upload")
def upload():
    f = request.files.get("file")
    if not f:
        return "no file", 400
    try:
        save_zip(f.read())
    except ValueError:
        return "invalid path", 400
    return "ok"


@app.get("/download")
def download():
    global last_hash, last_generated
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in DATA_DIR.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(DATA_DIR))
    data = buffer.getvalue()
    last_hash = hashlib.sha256(data).hexdigest()
    last_generated = time.time()
    return send_file(io.BytesIO(data), mimetype="application/zip", download_name="backup.zip")


@app.post("/verify")
def verify():
    global status_color
    data = request.get_json(silent=True) or {}
    client_hash = data.get("hash")
    client_ts = data.get("timestamp")
    if client_hash and client_hash == last_hash:
        status_color = "green"
        return {"status": "green"}
    if client_ts and last_generated and abs(client_ts - last_generated) <= 86400:
        status_color = "yellow"
        return {"status": "yellow"}
    status_color = "red"
    return {"status": "red"}


class ErrorFlagHandler(logging.Handler):
    def emit(self, record):
        global error_flag
        if record.levelno >= logging.ERROR:
            error_flag = True


app.logger.addHandler(ErrorFlagHandler())


def run_server():
    global error_flag
    try:
        app.run(host=HOST, port=PORT, ssl_context=(CERT_FILE, KEY_FILE))
    except Exception:
        error_flag = True


if __name__ == "__main__":
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    start_time = time.time()
    root = tk.Tk()
    root.title("Sync Server")
    root.geometry("300x120")
    BG, FG = "#000", "#0f0"
    root.configure(bg=BG)
    port_label = tk.Label(root, text=f"Port: {PORT}", bg=BG, fg=FG)
    port_label.pack(anchor="w")
    uptime_var = tk.StringVar()
    uptime_label = tk.Label(root, textvariable=uptime_var, bg=BG, fg=FG)
    uptime_label.pack(anchor="w")
    status_frame = tk.Frame(root, bg=BG)
    status_label = tk.Label(status_frame, text="Status:", bg=BG, fg=FG)
    status_label.pack(side="left")
    status_canvas = tk.Canvas(status_frame, width=20, height=20, bg=BG, highlightthickness=0)
    status_canvas.pack(side="left")
    status_dot = status_canvas.create_oval(2, 2, 18, 18, fill="red")
    status_frame.pack(anchor="w")

    def update():
        uptime = int(time.time() - start_time)
        uptime_var.set(f"Uptime: {uptime}s")
        color = status_color
        if not server_thread.is_alive():
            color = "red"
        elif error_flag and color != "red":
            color = "yellow"
        status_canvas.itemconfig(status_dot, fill=color)
        root.after(1000, update)

    update()
    root.mainloop()
