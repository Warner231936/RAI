
"""Discord interface for the Requiem AI."""

import os

import discord

from core import (
    USER_DATA,
    MEMORY_FILE,
    build_prompt,
    generate_response,
    get_user_entry,
    reload_global_memory,
    save_user_data,
    set_emotion,
    update_memory,
)


TOKEN = os.getenv("DISCORD_TOKEN")

import os
import json
from pathlib import Path

import discord
import requests

TOKEN = os.getenv("DISCORD_TOKEN")
KOBOLD_URL = os.getenv("KOBOLD_URL", "http://localhost:5001")

ASSIST_URL = os.getenv("KOBOLD_ASSIST_URL")  # optional smaller model


BASE_DIR = Path(__file__).parent
MEMORY_FILE = BASE_DIR / "memory.md"
USER_MEMORY_FILE = BASE_DIR / "user_memory.json"

# Load shared memory
if MEMORY_FILE.exists():
    GLOBAL_MEMORY = MEMORY_FILE.read_text()
else:
    GLOBAL_MEMORY = ""


# Load per-user data (history and emotion)
if USER_MEMORY_FILE.exists():
    USER_DATA = json.loads(USER_MEMORY_FILE.read_text())
else:
    USER_DATA = {}


def save_user_data() -> None:
    USER_MEMORY_FILE.write_text(json.dumps(USER_DATA, indent=2))


def get_user_entry(user_id: int) -> dict:
    """Return user data, migrating from legacy formats if needed."""
    entry = USER_DATA.setdefault(str(user_id), {"history": [], "emotion": "neutral"})
    if isinstance(entry, list):  # migrate older list-only history format
        entry = {"history": entry, "emotion": "neutral"}
        USER_DATA[str(user_id)] = entry
    entry.setdefault("history", [])
    entry.setdefault("emotion", "neutral")
    return entry

# Load per-user memories
if USER_MEMORY_FILE.exists():
    USER_MEMORIES = json.loads(USER_MEMORY_FILE.read_text())
else:
    USER_MEMORIES = {}

def save_user_memories() -> None:
    USER_MEMORY_FILE.write_text(json.dumps(USER_MEMORIES, indent=2))


intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")




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


def build_prompt(user_id: int, message: str) -> str:
    """Construct prompt with shared and per-user memory."""
    entry = get_user_entry(user_id)
    history = "".join(entry["history"])
    emotion = entry.get("emotion", "neutral")
    hint = assist_prompt(message)
    directives = f"[Emotion: {emotion}]"
    if hint:
        directives += f" [Hint: {hint}]"
    prompt = f"{GLOBAL_MEMORY}\n{directives}\n{history}User: {message}\nAI:"

def build_prompt(user_id: int, message: str) -> str:
    """Construct prompt with shared and per-user memory."""
    history = "".join(USER_MEMORIES.get(str(user_id), []))
    prompt = f"{GLOBAL_MEMORY}\n{history}User: {message}\nAI:"  # Use 'AI:' as the assistant marker

    return prompt


def update_memory(user_id: int, user_msg: str, ai_msg: str) -> None:

    entry = get_user_entry(user_id)
    entry["history"].append(f"User: {user_msg}\nAI: {ai_msg}\n")
    save_user_data()


def set_emotion(user_id: int, emotion: str) -> None:
    entry = get_user_entry(user_id)
    entry["emotion"] = emotion
    save_user_data()

    history = USER_MEMORIES.setdefault(str(user_id), [])
    history.append(f"User: {user_msg}\nAI: {ai_msg}\n")
    save_user_memories()



def generate_response(prompt: str) -> str:
    payload = {
        "prompt": prompt,
        "max_context_length": 2048,
        "max_length": 512,
        "temperature": 0.7,
        "top_p": 0.9,
        "stop_sequence": ["\nUser:"]
    }
    resp = requests.post(f"{KOBOLD_URL}/api/v1/generate", json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()["results"][0]["text"].strip()



@client.event
async def on_message(message: discord.Message):
    if message.author == client.user or message.author.bot:
        return



    content = message.content.strip()

    if content == "!forget":
        USER_DATA.pop(str(message.author.id), None)
        save_user_data()
        await message.channel.send("Your memory has been cleared.")
        return

    if content == "!reload":
        if getattr(message.author, "guild_permissions", None) and message.author.guild_permissions.administrator:

            if MEMORY_FILE.exists():
                reload_global_memory()

            global GLOBAL_MEMORY
            if MEMORY_FILE.exists():
                GLOBAL_MEMORY = MEMORY_FILE.read_text()

                await message.channel.send("Shared memory reloaded.")
            else:
                await message.channel.send("Memory file not found.")
        else:
            await message.channel.send("You do not have permission to reload memory.")
        return

    if content.startswith("!emotion"):
        parts = content.split(maxsplit=1)
        if len(parts) == 2:
            set_emotion(message.author.id, parts[1])
            await message.channel.send(f"Emotion set to {parts[1]}.")
        else:
            current = get_user_entry(message.author.id)["emotion"]
            await message.channel.send(f"Current emotion: {current}")
        return

    if content == "!help":
        await message.channel.send("Commands: !forget, !reload, !emotion <mood>")
        return


    prompt = build_prompt(message.author.id, message.content)
    try:
        reply = generate_response(prompt)
    except Exception as exc:  # pragma: no cover - network errors
        await message.channel.send(f"Error: {exc}")
        return

    update_memory(message.author.id, message.content, reply)
    await message.channel.send(reply)


if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN not set")
    client.run(TOKEN)

