"""Shared utilities for interacting with KoboldCPP and user memory.

This module centralises the logic used by both the Discord bot and the
optional web UI so that they can operate on the same memory store and
generation settings while handling concurrent access from multiple users.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Dict

import requests

# Environment configuration -------------------------------------------------

KOBOLD_URL = os.getenv("KOBOLD_URL", "http://localhost:5001")
ASSIST_URL = os.getenv("KOBOLD_ASSIST_URL")  # optional secondary model

BASE_DIR = Path(__file__).parent
MEMORY_FILE = BASE_DIR / "memory.md"
USER_MEMORY_FILE = BASE_DIR / "user_memory.json"

_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Persistent storage helpers

def _load_global_memory() -> str:
    return MEMORY_FILE.read_text() if MEMORY_FILE.exists() else ""


GLOBAL_MEMORY = _load_global_memory()

if USER_MEMORY_FILE.exists():
    USER_DATA: Dict[str, Dict[str, Any]] = json.loads(USER_MEMORY_FILE.read_text())
else:
    USER_DATA = {}


def save_user_data() -> None:
    with _LOCK:
        USER_MEMORY_FILE.write_text(json.dumps(USER_DATA, indent=2))


def get_user_entry(user_id: Any) -> Dict[str, Any]:
    """Return user data, migrating from legacy formats if needed."""

    uid = str(user_id)
    with _LOCK:
        entry = USER_DATA.setdefault(uid, {"history": [], "emotion": "neutral"})
        if isinstance(entry, list):  # migrate older list-only history format
            entry = {"history": entry, "emotion": "neutral"}
            USER_DATA[uid] = entry
        entry.setdefault("history", [])
        entry.setdefault("emotion", "neutral")
    return entry


def set_emotion(user_id: Any, emotion: str) -> None:
    entry = get_user_entry(user_id)
    with _LOCK:
        entry["emotion"] = emotion
    save_user_data()


def update_memory(user_id: Any, user_msg: str, ai_msg: str) -> None:
    entry = get_user_entry(user_id)
    with _LOCK:
        entry["history"].append(f"User: {user_msg}\nAI: {ai_msg}\n")
    save_user_data()


def reload_global_memory() -> str:
    global GLOBAL_MEMORY
    GLOBAL_MEMORY = _load_global_memory()
    return GLOBAL_MEMORY


# ---------------------------------------------------------------------------
# Generation helpers

def assist_prompt(message: str) -> str:
    """Use the secondary model to provide a brief hint."""

    if not ASSIST_URL:
        return ""
    payload = {
        "prompt": (
            "Given the user message below, suggest a short emotional hint for the main AI to respond with more feeling.\n"
            f"Message: {message}\nHint:"
        ),
        "max_length": 60,
        "temperature": 0.8,
        "top_p": 0.9,
        "stop_sequence": ["\n"],
    }
    try:
        resp = requests.post(f"{ASSIST_URL}/api/v1/generate", json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()["results"][0]["text"].strip()
    except Exception:
        return ""


def build_prompt(user_id: Any, message: str) -> str:
    """Construct prompt with shared and per-user memory."""

    entry = get_user_entry(user_id)
    history = "".join(entry["history"])
    emotion = entry.get("emotion", "neutral")
    hint = assist_prompt(message)
    directives = f"[Emotion: {emotion}]"
    if hint:
        directives += f" [Hint: {hint}]"
    prompt = f"{GLOBAL_MEMORY}\n{directives}\n{history}User: {message}\nAI:"
    return prompt


def generate_response(prompt: str) -> str:
    payload = {
        "prompt": prompt,
        "max_context_length": 2048,
        "max_length": 512,
        "temperature": 0.7,
        "top_p": 0.9,
        "stop_sequence": ["\nUser:"],
    }
    resp = requests.post(f"{KOBOLD_URL}/api/v1/generate", json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()["results"][0]["text"].strip()

