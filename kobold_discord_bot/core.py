"""Shared utilities for Requiem AI bots and web UI."""
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
from langdetect import detect, LangDetectException
from deep_translator import GoogleTranslator

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

KOBOLD_URL = os.getenv("KOBOLD_URL", "http://localhost:5001").rstrip("/")
ASSIST_URL = os.getenv("KOBOLD_ASSIST_URL", "").rstrip("/")
SD_URL = os.getenv("SD_URL", "http://localhost:7860").rstrip("/")

BASE_DIR = Path(__file__).parent
MEMORY_FILE = BASE_DIR / "memory.md"
USER_MEMORY_FILE = BASE_DIR / "user_memory.json"
MEM_EXPORT_PATH = Path(
    os.getenv("MEM_EXPORT_PATH", str(BASE_DIR / "Requiem_Memory_Export.md"))
)
GO2_DATA_FILE = BASE_DIR / "go2_data.json"

SYSTEM_PROMPT = (
    "You are Requiem. Be concise, multilingual (mirror the user's language), "
    "helpful, and accurate. If the user mixes languages, answer in their dominant "
    "language. Avoid roleplay unless asked."
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
# ---------------------------------------------------------------------------

def _load_global_memory() -> str:
    return MEMORY_FILE.read_text(encoding="utf-8") if MEMORY_FILE.exists() else ""


def reload_global_memory() -> str:
    global GLOBAL_MEMORY
    GLOBAL_MEMORY = _load_global_memory()
    return GLOBAL_MEMORY


GLOBAL_MEMORY = _load_global_memory()


def _load_go2_data() -> Dict[str, Any]:
    return (
        json.loads(GO2_DATA_FILE.read_text(encoding="utf-8"))
        if GO2_DATA_FILE.exists()
        else {}
    )


GO2_DATA = _load_go2_data()

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
    """Return user data, migrating legacy formats if needed."""

    uid = str(user_id)
    with _LOCK:
        entry = USER_DATA.setdefault(uid, {"history": [], "emotion": "neutral", "summary": ""})
    if isinstance(entry, list):
        entry = {"history": entry, "emotion": "neutral", "summary": ""}
        with _LOCK:
            USER_DATA[uid] = entry
    entry.setdefault("history", [])
    entry.setdefault("emotion", "neutral")
    entry.setdefault("summary", "")
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


# ---------------------------------------------------------------------------
# Knowledge base and generation helpers
# ---------------------------------------------------------------------------

def lookup_go2(message: str, max_items: int = 3) -> str:
    """Return Galaxy Online 2 facts relevant to ``message``."""

    if not GO2_DATA:
        return ""
    words = set(re.findall(r"\w+", message.lower()))
    if not words:
        return ""
    hits: List[str] = []
    for cat, items in GO2_DATA.items():
        if not isinstance(items, dict):
            continue
        for name, info in items.items():
            text = f"{name} {info}".lower()
            if any(w in text for w in words):
                hits.append(f"{name.title()} ({cat}): {info}")
                if len(hits) >= max_items:
                    return "\n".join(hits)
    return "\n".join(hits)


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
    with _SEMAPHORE:
        resp = _SESSION.post(
            f"{ASSIST_URL}/api/v1/generate", json=payload, timeout=HTTP_TIMEOUT
        )
    resp.raise_for_status()
    js = resp.json()
    return (js.get("results", [{}])[0].get("text") or "").strip()


def generate_response(prompt: str) -> str:
    payload = {
        "prompt": prompt,
        "max_context_length": 2048,
        "max_length": 512,
        "temperature": 0.7,
        "top_p": 0.9,
        "stop_sequence": ["\nUser:"],
    }
    with _SEMAPHORE:
        resp = _SESSION.post(
            f"{KOBOLD_URL}/api/v1/generate", json=payload, timeout=HTTP_TIMEOUT
        )
    resp.raise_for_status()
    js = resp.json()
    return (js.get("results", [{}])[0].get("text") or "").strip()


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


# ---------------------------------------------------------------------------
# Multilingual helpers
# ---------------------------------------------------------------------------

def detect_language(text: str) -> str:
    try:
        return detect(text)
    except LangDetectException:  # pragma: no cover - nondeterministic
        return "en"


def translate_text(text: str, src: str, dest: str) -> str:
    if src == dest:
        return text
    try:
        return GoogleTranslator(source=src, target=dest).translate(text)
    except Exception:
        return text


__all__ = [
    "MAX_WORKERS",
    "MEM_EXPORT_PATH",
    "MEMORY_FILE",
    "USER_DATA",
    "SYSTEM_PROMPT",
    "assist_hint",
    "detect_language",
    "generate_response",
    "get_user_entry",
    "lookup_go2",
    "reload_global_memory",
    "save_user_data",
    "set_emotion",
    "translate_text",
    "txt2img",
    "update_memory",
]
