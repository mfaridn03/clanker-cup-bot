import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

from irc.manager import SessionManager
from lobby import LobbyManager

load_dotenv()

ALLOWED_SERVER = 1527856371884884048
STAFF_ROLE = 1527871437489045514

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())
bot.lobbies = LobbyManager()


async def _on_irc_privmsg(nick: str, target: str, message: str) -> None:
    if nick.casefold() != "banchobot":
        return
    lobby = bot.lobbies.get_by_irc(target)
    if lobby is None:
        return
    channel = bot.get_channel(lobby.discord_channel_id)
    if not isinstance(channel, discord.TextChannel):
        return
    await channel.send(message)


bot.irc = SessionManager(on_privmsg=_on_irc_privmsg)

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


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return
    lobby = bot.lobbies.get_by_discord(message.channel.id)
    if lobby is None:
        return
    if not message.content:
        return
    session = bot.irc.get(lobby.owner_id)
    if session is None:
        return
    await session.send_privmsg(lobby.irc_channel, message.content)


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


@bot.tree.command(name="make", description="make lobby")
async def make(ctx: discord.Interaction, lobby_name: str):
    if not _is_allowed(ctx):
        return

    # the rest


bot.run(os.getenv("BOT_TOKEN"))
