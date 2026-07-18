import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

from irc.manager import SessionManager

load_dotenv()

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())
bot.irc = SessionManager()

ALLOWED_SERVER = 1527856371884884048
STAFF_ROLE = 1527871437489045514

_original_close = bot.close


async def _close_with_irc() -> None:
    await bot.irc.disconnect_all()
    await _original_close()


bot.close = _close_with_irc  # type: ignore[method-assign]


def _is_allowed(ctx: discord.Interaction) -> bool:
    if ctx.guild_id != ALLOWED_SERVER:
        return False
    if not isinstance(ctx.user, discord.Member):
        return False
    return STAFF_ROLE in [role.id for role in ctx.user.roles]


@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")


@bot.tree.command(name="ping", description="pong!")
async def ping(ctx: discord.Interaction):
    await ctx.response.send_message("pong!", ephemeral=True)


@bot.tree.command(name="register")
async def register(ctx: discord.Interaction, nick: str, irc_password: str):
    if not _is_allowed(ctx):
        return

    await ctx.response.send_message("register cmd", ephemeral=True)


@bot.tree.command(name="connect", description="connect to irc")
async def connect(ctx: discord.Interaction):
    if not _is_allowed(ctx):
        return

    nick = os.getenv("DEV_NICK")
    password = os.getenv("DEV_IRCPW")
    if not nick or not password:
        await ctx.response.send_message("missing DEV_NICK or DEV_IRCPW", ephemeral=True)
        return

    nick = nick.strip('"')
    password = password.strip('"')

    try:
        await bot.irc.connect(ctx.user.id, nick, password)
    except RuntimeError as exc:
        await ctx.followup.send(str(exc), ephemeral=True)
        return
    except Exception as exc:
        await ctx.followup.send(f"connect failed: {exc}", ephemeral=True)
        return

    await ctx.followup.send(f"connected to Bancho as {nick}", ephemeral=True)


@bot.tree.command(name="disconnect", description="disconnect from irc")
async def disconnect(ctx: discord.Interaction):
    if not _is_allowed(ctx):
        return

    ok = await bot.irc.disconnect(ctx.user.id)
    if ok:
        await ctx.followup.send("disconnected", ephemeral=True)
    else:
        await ctx.followup.send("not connected", ephemeral=True)


bot.run(os.getenv("BOT_TOKEN"))
