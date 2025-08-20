"""Shared utilities for interacting with KoboldCPP and user memory.

This module centralises logic used by both the Discord bot and the optional
web UI so that they can operate on the same memory store while handling
concurrent access from multiple users.
"""

from __future__ import annotations

import base64
import json
import os
import re
import threading
from pathlib import Path
from typing import Any, Dict, List

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Environment configuration -------------------------------------------------

KOBOLD_URL = os.getenv("KOBOLD_URL", "http://localhost:5001").rstrip("/")
ASSIST_URL = os.getenv("KOBOLD_ASSIST_URL", "").rstrip("/")
SD_URL = os.getenv("SD_URL", "http://localhost:7860").rstrip("/")

BASE_DIR = Path(__file__).parent
MEMORY_FILE = BASE_DIR / "memory.md"
USER_MEMORY_FILE = BASE_DIR / "user_memory.json"
MEM_EXPORT_PATH = Path(
    os.getenv("MEM_EXPORT_PATH", str(BASE_DIR / "Requiem_Memory_Export.md"))
)

SYSTEM_PROMPT = (
    "You are Requiem. Be concise, multilingual (mirror the user's language), helpful, and accurate. "
    "If the user mixes languages, answer in their dominant language. Avoid roleplay unless asked."
)

STOP_SEQ = ["<|im_end|>", "<|im_start|>user"]

MAX_WORKERS = int(os.getenv("MAX_WORKERS", "4"))
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "60"))

_LOCK = threading.Lock()
_SEMAPHORE = threading.Semaphore(MAX_WORKERS)

_SESSION = requests.Session()
_ADAPTER = HTTPAdapter(
    pool_connections=MAX_WORKERS,
    pool_maxsize=MAX_WORKERS,
    max_retries=Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504]),
)
_SESSION.mount("http://", _ADAPTER)
_SESSION.mount("https://", _ADAPTER)


# ---------------------------------------------------------------------------
# Persistent storage helpers

def _load_global_memory() -> str:
    return MEMORY_FILE.read_text(encoding="utf-8") if MEMORY_FILE.exists() else ""


GLOBAL_MEMORY = _load_global_memory()

if USER_MEMORY_FILE.exists():
    USER_DATA: Dict[str, Any] = json.loads(USER_MEMORY_FILE.read_text(encoding="utf-8"))
else:
    USER_DATA = {}


def save_user_data() -> None:
    with _LOCK:
        USER_MEMORY_FILE.write_text(
            json.dumps(USER_DATA, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def get_user_entry(user_id: Any) -> Dict[str, Any]:
    """Return user data; migrate legacy formats if needed."""

    uid = str(user_id)
    with _LOCK:
        entry = USER_DATA.setdefault(uid, {"history": [], "emotion": "neutral"})
    if isinstance(entry, list):
        entry = {"history": entry, "emotion": "neutral"}
        with _LOCK:
            USER_DATA[uid] = entry
    entry.setdefault("history", [])
    entry.setdefault("emotion", "neutral")

    # Migrate legacy string history ("User:...\nAI:...")
    hist = entry["history"]
    migrated: List[Dict[str, str]] = []
    changed = False
    for item in hist:
        if isinstance(item, dict) and "role" in item and "content" in item:
            migrated.append(item)
            continue
        if isinstance(item, str):
            m = re.findall(r"(User|AI):\s*(.*?)(?:\n|$)", item, flags=re.S)
            if m:
                for role, content in m:
                    migrated.append(
                        {
                            "role": "user" if role.lower() == "user" else "assistant",
                            "content": content.strip(),
                        }
                    )
                changed = True
            else:
                migrated.append({"role": "user", "content": item.strip()})
                changed = True
        else:
            changed = True
    if changed:
        entry["history"] = migrated
        save_user_data()
    return entry


def set_emotion(user_id: Any, emotion: str) -> None:
    entry = get_user_entry(user_id)
    with _LOCK:
        entry["emotion"] = emotion
    save_user_data()


def update_memory(user_id: Any, user_msg: str, ai_msg: str) -> None:
    entry = get_user_entry(user_id)
    with _LOCK:
        entry["history"].append({"role": "user", "content": user_msg})
        entry["history"].append({"role": "assistant", "content": ai_msg})
        if len(entry["history"]) > 200:
            entry["history"] = entry["history"][-200:]
    save_user_data()


def reload_global_memory() -> str:
    global GLOBAL_MEMORY
    GLOBAL_MEMORY = _load_global_memory()
    return GLOBAL_MEMORY


# ---------------------------------------------------------------------------
# Generation helpers

def assist_hint(user_message: str) -> str:
    if not ASSIST_URL:
        return ""
    payload = {
        "prompt": (
            "Given the user message below, suggest a short emotional/style hint to help the main assistant "
            "respond with more feeling (5-10 words, no quotes).\n"
            f"Message: {user_message}\nHint:"
        ),
        "max_length": 60,
        "temperature": 0.8,
        "top_p": 0.9,
        "stop_sequence": ["\n"],
    }
    try:
        with _SEMAPHORE:
            resp = _SESSION.post(
                f"{ASSIST_URL}/api/v1/generate", json=payload, timeout=HTTP_TIMEOUT
            )
        resp.raise_for_status()
        js = resp.json()
        return (js.get("results", [{}])[0].get("text", "") or "").strip()
    except Exception:
        return ""


def chatml_format(messages: List[Dict[str, str]]) -> str:
    out = []
    for m in messages:
        role = m.get("role")
        if role not in ("system", "user", "assistant"):
            role = "user"
        out.append(f"<|im_start|>{role}\n{m.get('content', '')}\n<|im_end|>")
    out.append("<|im_start|>assistant\n")
    return "\n".join(out)


def build_prompt(user_id: Any, message: str, hint: str = "") -> str:
    entry = get_user_entry(user_id)
    emotion = entry.get("emotion", "neutral")
    sys_lines = [SYSTEM_PROMPT]
    if GLOBAL_MEMORY:
        sys_lines.append("\n# Shared Memory\n" + GLOBAL_MEMORY.strip())
    sys_lines.append(f"\n[Emotion: {emotion}]")
    if hint:
        sys_lines.append(f"[Hint: {hint}]")
    system = {"role": "system", "content": "\n".join(sys_lines).strip()}

    hist_msgs: List[Dict[str, str]] = []
    for turn in entry["history"][-20:]:
        if isinstance(turn, dict) and "role" in turn and "content" in turn:
            hist_msgs.append({"role": turn["role"], "content": turn["content"]})

    messages = hist_msgs + [{"role": "user", "content": message}]
    return chatml_format([system] + messages)


def generate_response(prompt: str) -> str:
    payload = {
        "prompt": prompt,
        "max_context_length": 8192,
        "max_length": 350,
        "temperature": 0.75,
        "top_p": 0.9,
        "typical_p": 1.0,
        "rep_pen": 1.12,
        "rep_pen_range": 128,
        "stop_sequence": STOP_SEQ,
        "frmttriminc": True,
    }
    with _SEMAPHORE:
        resp = _SESSION.post(
            f"{KOBOLD_URL}/api/v1/generate", json=payload, timeout=HTTP_TIMEOUT
        )
    resp.raise_for_status()
    js = resp.json()
    res = js.get("results") or []
    if res and isinstance(res, list):
        return (res[0].get("text") or "").strip()
    return ""


def txt2img(prompt: str, steps: int = 22, w: int = 640, h: int = 640, cfg: float = 7.0) -> bytes:
    payload = {
        "prompt": prompt,
        "steps": steps,
        "width": w,
        "height": h,
        "cfg_scale": cfg,
        "sampler_name": "Euler a",
    }
    with _SEMAPHORE:
        resp = _SESSION.post(
            f"{SD_URL}/sdapi/v1/txt2img", json=payload, timeout=HTTP_TIMEOUT
        )
    resp.raise_for_status()
    b64 = resp.json()["images"][0]
    return base64.b64decode(b64)


__all__ = [
    "MAX_WORKERS",
    "ASSIST_URL",
    "BASE_DIR",
    "GLOBAL_MEMORY",
    "KOBOLD_URL",
    "MEMORY_FILE",
    "MEM_EXPORT_PATH",
    "SD_URL",
    "STOP_SEQ",
    "USER_DATA",
    "assist_hint",
    "build_prompt",
    "chatml_format",
    "generate_response",
    "get_user_entry",
    "reload_global_memory",
    "save_user_data",
    "set_emotion",
    "txt2img",
    "update_memory",
]

