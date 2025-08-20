"""Discord interface for the Requiem AI."""

import asyncio
import os

import discord
from discord.ext import commands

from core import (
    MAX_WORKERS,
    MEM_EXPORT_PATH,
    MEMORY_FILE,
    USER_DATA,
    assist_hint,
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


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID {bot.user.id})")


@bot.command(name="helpme")
async def helpme(ctx: commands.Context) -> None:
    await ctx.reply(
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


if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN not set")
    bot.run(TOKEN)

