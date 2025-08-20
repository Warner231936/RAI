
"""Discord interface for the Requiem AI."""
from __future__ import annotations
"""Discord interface for the Requiem AI."""
import asyncio
import os
import aiohttp
import discord
from discord.ext import commands
import core
import discord
from discord.ext import commands

from core import (
    MAX_WORKERS,
    MEM_EXPORT_PATH,
    MEMORY_FILE,
    USER_DATA,
    SYSTEM_PROMPT,
    detect_language,
    get_user_entry,
    lookup_go2,
    reload_global_memory,
    save_user_data,
    set_emotion,
    translate_text,
    txt2img,
    update_memory,
)
from orchestrator import Orchestrator

    assist_hint,

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
    txt2img,
    update_memory,
)



TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

GENERATION_SEMAPHORE = asyncio.Semaphore(MAX_WORKERS)


_SESSION: aiohttp.ClientSession | None = None
ORCH: Orchestrator | None = None


@bot.event
async def on_ready():
    global _SESSION, ORCH
    if _SESSION is None or _SESSION.closed:
        _SESSION = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300))
    ORCH = Orchestrator(SYSTEM_PROMPT, core.GLOBAL_MEMORY, _SESSION)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID {bot.user.id})")


@bot.command(name="helpme")
async def helpme(ctx: commands.Context) -> None:
    await ctx.reply(

        "Commands: !forget, !reload, !emotion <mood>, !img <prompt>, !go2 <text>, !memoryfile, !memoryhere, !anchors, !memfind <text>\n"
        "Commands: !forget, !reload, !emotion <mood>, !img <prompt>, !memoryfile, !memoryhere, !anchors, !memfind <text>\n"
        "Talk to me by mentioning me or just typing—I'll answer here."
    )


@bot.command(name="forget")
async def forget(ctx: commands.Context) -> None:
    USER_DATA.pop(str(ctx.author.id), None)
    save_user_data()
    await ctx.reply("Your memory is cleared.")


@bot.command(name="reload")
@commands.has_permissions(administrator=True)
async def reload_cmd(ctx: commands.Context) -> None:
    if MEMORY_FILE.exists():
        reload_global_memory()
        if ORCH:
            ORCH.gmem = core.GLOBAL_MEMORY
        await ctx.reply("Shared memory reloaded.")
    else:
        await ctx.reply("memory.md not found.")


@reload_cmd.error
async def reload_err(ctx: commands.Context, exc: Exception) -> None:
    await ctx.reply("You lack permission to reload memory.")


@bot.command(name="emotion")
async def emotion(ctx: commands.Context, *, mood: str | None = None) -> None:
    if mood:
        set_emotion(ctx.author.id, mood.strip()[:40])
        await ctx.reply(f"Emotion set to **{mood}**.")
    else:
        current = get_user_entry(ctx.author.id)["emotion"]
        await ctx.reply(f"Current emotion: **{current}**")


@bot.command(name="img")
async def img_cmd(ctx: commands.Context, *, prompt: str = "") -> None:
    if not prompt:
        return await ctx.reply("Usage: `!img <prompt>`")
    await ctx.channel.typing()
    try:
        async with GENERATION_SEMAPHORE:
            png = await asyncio.to_thread(txt2img, prompt)
    except Exception as e:  # pragma: no cover - network errors
        return await ctx.reply(f"Image error: {e}")
    await ctx.reply(
        content=f"**Prompt:** {prompt}",
        file=discord.File(fp=bytes(png), filename="image.png"),
    )


@bot.command(name="go2")
async def go2_cmd(ctx: commands.Context, *, q: str = "") -> None:
    if not q:
        return await ctx.reply("Usage: `!go2 <text>`")
    hits = lookup_go2(q, max_items=5)
    if not hits:
        await ctx.reply(f"No info for **{q}**")
    else:
        await ctx.reply(f"**GO2 Info:**\n{hits}")

@bot.command(name="memoryfile")
async def memoryfile_cmd(ctx: commands.Context) -> None:
    if not MEM_EXPORT_PATH.exists():
        return await ctx.reply(f"Memory file not found: `{MEM_EXPORT_PATH}`")
    try:
        await ctx.author.send(
            file=discord.File(str(MEM_EXPORT_PATH), filename=MEM_EXPORT_PATH.name)
        )
        await ctx.reply("Sent you a DM with the file.")
    except discord.Forbidden:
        await ctx.reply("I can’t DM you. Use `!memoryhere` to post it in-channel.")


@bot.command(name="memoryhere")
async def memoryhere_cmd(ctx: commands.Context) -> None:
    if not MEM_EXPORT_PATH.exists():
        return await ctx.reply(f"Memory file not found: `{MEM_EXPORT_PATH}`")
    await ctx.reply(
        file=discord.File(str(MEM_EXPORT_PATH), filename=MEM_EXPORT_PATH.name)
    )


def _extract_anchors(md: str, max_items: int = 12) -> str:
    lines = [ln.strip() for ln in md.splitlines()]
    hits = [ln for ln in lines if "Anchor" in ln]
    seen: set[str] = set()
    out: list[str] = []
    for h in hits:
        if h not in seen:
            out.append(h)
            seen.add(h)
    return "\n".join(f"• {x}" for x in out[:max_items]) or "(no anchors found)"


@bot.command(name="anchors")
async def anchors_cmd(ctx: commands.Context) -> None:
    if not MEM_EXPORT_PATH.exists():
        return await ctx.reply("(no memory export found)")
    text = MEM_EXPORT_PATH.read_text(encoding="utf-8")
    await ctx.reply(f"**Anchors (top)**\n{_extract_anchors(text)}")


@bot.command(name="memfind")
async def memfind_cmd(ctx: commands.Context, *, q: str = "") -> None:
    if not q:
        return await ctx.reply("Usage: `!memfind <text>`")
    if not MEM_EXPORT_PATH.exists():
        return await ctx.reply("(no memory export found)")
    text = MEM_EXPORT_PATH.read_text(encoding="utf-8")
    matches: list[str] = []
    for i, ln in enumerate(text.splitlines(), 1):
        if q.lower() in ln.lower():
            matches.append(f"`L{i:>4}` {ln[:180]}")
            if len(matches) >= 10:
                break
    if not matches:
        return await ctx.reply(f"No hits for **{q}**")
    await ctx.reply(f"**Search:** {q}\n" + "\n".join(matches))


@bot.event
async def on_message(message: discord.Message) -> None:
    await bot.process_commands(message)
    if message.author.bot:
        return
    content = message.content.strip()
    if content.startswith("!"):
        return

    if ORCH is None:
        return await message.channel.send("Model not ready")

    await message.channel.typing()
    entry = get_user_entry(message.author.id)
    lang = detect_language(content)
    content_en = translate_text(content, lang, "en")
    kb = lookup_go2(content_en)
    async with GENERATION_SEMAPHORE:
        try:
            result = await ORCH.handle(
                message.author.id,
                entry["history"],
                content_en,
                kb,
                entry.get("summary", ""),
            )
        except Exception as exc:  # pragma: no cover - network errors
            return await message.channel.send(f"Error: {exc}")
    reply_en = result.final
    reply = translate_text(reply_en, "en", lang)
    update_memory(message.author.id, content_en, reply_en)
    for chunk in (reply[i : i + 1900] for i in range(0, len(reply), 1900)):
        await message.channel.send(chunk)
    if result.intent.flags.get("needs_image"):
        async with GENERATION_SEMAPHORE:
            try:
                png = await asyncio.to_thread(txt2img, content)
            except Exception as exc:  # pragma: no cover - network errors
                await message.channel.send(f"Image error: {exc}")
            else:
                await message.channel.send(file=discord.File(fp=bytes(png), filename="image.png"))
    await message.channel.typing()
    async with GENERATION_SEMAPHORE:
        hint = await asyncio.to_thread(assist_hint, content)
        prompt = build_prompt(message.author.id, content, hint)
        try:
            reply = await asyncio.to_thread(generate_response, prompt)
        except Exception as exc:  # pragma: no cover - network errors
            return await message.channel.send(f"Error: {exc}")
    update_memory(message.author.id, content, reply)
    for chunk in (reply[i : i + 1900] for i in range(0, len(reply), 1900)):
        await message.channel.send(chunk)

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
    bot.run(TOKEN)


    client.run(TOKEN)
