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

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")


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

