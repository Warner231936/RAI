import os
import json
from pathlib import Path

import discord
import requests

TOKEN = os.getenv("DISCORD_TOKEN")
KOBOLD_URL = os.getenv("KOBOLD_URL", "http://localhost:5001")

BASE_DIR = Path(__file__).parent
MEMORY_FILE = BASE_DIR / "memory.md"
USER_MEMORY_FILE = BASE_DIR / "user_memory.json"

# Load shared memory
if MEMORY_FILE.exists():
    GLOBAL_MEMORY = MEMORY_FILE.read_text()
else:
    GLOBAL_MEMORY = ""

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


def build_prompt(user_id: int, message: str) -> str:
    """Construct prompt with shared and per-user memory."""
    history = "".join(USER_MEMORIES.get(str(user_id), []))
    prompt = f"{GLOBAL_MEMORY}\n{history}User: {message}\nAI:"  # Use 'AI:' as the assistant marker
    return prompt


def update_memory(user_id: int, user_msg: str, ai_msg: str) -> None:
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
