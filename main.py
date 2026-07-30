import os
import re

import discord
from discord.ext import commands
from dotenv import load_dotenv

import credentials
from irc.manager import SessionManager
from irc.session import verify_credentials
from lobby import Lobby, LobbyManager, RateLimitedWebhook

load_dotenv()

LOBBY_CATEGORY_ID = 1527880192561774592
ALLOWED_SERVER = 1527856371884884048
STAFF_ROLE = 1527871437489045514
CREATED_MATCH_RE = re.compile(
    r"Created the tournament match https://osu\.ppy\.sh/mp/(\d+)"
)

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())
bot.lobbies = LobbyManager()


async def _on_irc_privmsg(nick: str, target: str, message: str) -> None:
    lobby = bot.lobbies.get_by_irc(target)
    if lobby is None:
        return
    lobby.enqueue_irc(nick, message)


async def _on_irc_part(_nick: str, channel: str) -> None:
    lobby = bot.lobbies.remove_by_irc(channel)
    if lobby is None:
        return
    print(f"[lobby] parted {channel}, bridge removed")
    discord_channel = bot.get_channel(lobby.discord_channel_id)

    if isinstance(discord_channel, discord.TextChannel):
        await discord_channel.send("Match closed")
        await discord_channel.edit(name=f"closed-{discord_channel.name}")


bot.irc = SessionManager(on_privmsg=_on_irc_privmsg, on_part=_on_irc_part)

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
    if message.author.id not in lobby.refs:
        return
    if not message.content:
        return
    session = bot.irc.get(lobby.owner_id)
    if session is None:
        return
    await session.send_privmsg(lobby.irc_channel, message.clean_content)


@bot.tree.command(name="ping", description="pong!")
async def ping(ctx: discord.Interaction):
    await ctx.response.send_message("pong!", ephemeral=True)


@bot.tree.command(name="addref", description="add additional ref to the lobby")
async def addref(ctx: discord.Interaction, member: discord.Member):
    if not _is_allowed(ctx):
        return

    await ctx.response.defer(ephemeral=False)

    lobby = bot.lobbies.get_by_discord(ctx.channel_id)
    if lobby is None:
        await ctx.followup.send("not a lobby channel", ephemeral=False)
        return

    session = bot.irc.get(ctx.user.id)
    if session is None:
        await ctx.followup.send("not connected - run /connect first", ephemeral=True)
        return

    if ctx.user.id != lobby.owner_id:
        await ctx.followup.send("only the lobby owner can add refs", ephemeral=False)
        return

    if member.id in lobby.refs:
        await ctx.followup.send(f"{member.mention} is already a ref on this lobby", ephemeral=False)
        return

    creds = await credentials.load(member.id)
    if creds is None:
        await ctx.followup.send(f"{member.mention} is not registered", ephemeral=False)
        return

    nick = creds["nick"].replace(" ", "_")
    await session.send_privmsg(lobby.irc_channel, f"!mp addref {nick}")
    lobby.refs.append(member.id)
    await ctx.followup.send(f"added {member.mention} as a ref", ephemeral=False)


@bot.tree.command(name="register", description="store Bancho IRC credentials")
async def register(ctx: discord.Interaction, nick: str, irc_password: str):
    if not _is_allowed(ctx):
        return

    await ctx.response.defer(ephemeral=True)
    try:
        await verify_credentials(nick, irc_password)
    except Exception as exc:
        await ctx.followup.send(f"registration failed: {exc}", ephemeral=True)
        return

    await credentials.save(ctx.user.id, nick, irc_password)
    await ctx.followup.send(f"registered as {nick.replace(' ', '_')}", ephemeral=True)


@bot.tree.command(name="connect", description="connect to irc")
async def connect(ctx: discord.Interaction):
    if not _is_allowed(ctx):
        return

    creds = await credentials.load(ctx.user.id)
    if creds is None:
        await ctx.response.send_message("not registered - run /register first", ephemeral=True)
        return

    await ctx.response.defer(ephemeral=True)
    try:
        await bot.irc.connect(ctx.user.id, creds["nick"], creds["password"])
    except RuntimeError as exc:
        await ctx.followup.send(str(exc), ephemeral=True)
        return
    except Exception as exc:
        await ctx.followup.send(f"connect failed: {exc}", ephemeral=True)
        return

    await ctx.followup.send(f"connected to Bancho as {creds['nick'].replace(' ', '_')}", ephemeral=True)


@bot.tree.command(name="disconnect", description="disconnect from irc")
async def disconnect(ctx: discord.Interaction):
    if not _is_allowed(ctx):
        return

    await ctx.response.defer(ephemeral=True)
    ok = await bot.irc.disconnect(ctx.user.id)
    if ok:
        await ctx.followup.send("disconnected", ephemeral=True)
    else:
        await ctx.followup.send("not connected", ephemeral=True)


@bot.tree.command(name="make", description="make lobby")
async def make(ctx: discord.Interaction, lobby_name: str):
    if not _is_allowed(ctx):
        return

    await ctx.response.defer(ephemeral=False)

    session = bot.irc.get(ctx.user.id)
    if session is None:
        await ctx.followup.send("not connected - run /connect first", ephemeral=True)
        return

    if ctx.guild is None:
        await ctx.followup.send("must be used in a server", ephemeral=True)
        return

    category = ctx.guild.get_channel(LOBBY_CATEGORY_ID)
    if not isinstance(category, discord.CategoryChannel):
        await ctx.followup.send("lobby category not found", ephemeral=True)
        return

    def _is_created(nick: str, _target: str, message: str) -> bool:
        return nick.casefold() == "banchobot" and CREATED_MATCH_RE.search(message) is not None

    try:
        await session.send_privmsg("BanchoBot", f"!mp make {lobby_name}")
        _nick, _target, reply = await session.wait_privmsg(_is_created, timeout=15.0)
    except TimeoutError:
        await ctx.followup.send("timed out waiting for BanchoBot", ephemeral=True)
        return
    except Exception as exc:
        await ctx.followup.send(f"make failed: {exc}", ephemeral=True)
        return

    match = CREATED_MATCH_RE.search(reply)
    if match is None:
        await ctx.followup.send(f"unexpected BanchoBot reply: {reply}", ephemeral=True)
        return

    lobby_id = match.group(1)
    irc_channel = f"#mp_{lobby_id}"
    match_url = f"https://osu.ppy.sh/mp/{lobby_id}"

    try:
        channel = await category.create_text_channel(f"mp-{lobby_id}", topic=lobby_name)
    except Exception as exc:
        await ctx.followup.send(f"created match {match_url} but Discord channel failed: {exc}", ephemeral=True)
        return

    try:
        banchobot_hook = await channel.create_webhook(name="BanchoBot")
        other_hook = await channel.create_webhook(name="IRC")
    except Exception as exc:
        await ctx.followup.send(
            f"created match {match_url} and channel {channel.mention} but webhooks failed: {exc}",
            ephemeral=True,
        )
        return

    bot.lobbies.add(
        Lobby(
            lobby_id=lobby_id,
            irc_channel=irc_channel,
            discord_channel_id=channel.id,
            owner_id=ctx.user.id,
            banchobot_webhook=RateLimitedWebhook(banchobot_hook),
            other_webhook=RateLimitedWebhook(other_hook),
        )
    )

    await ctx.followup.send(
        f"lobby ready: {match_url}\nchannel: {channel.mention}",
        ephemeral=False,
    )

    await channel.send(ctx.user.mention)
    await session.send_privmsg(irc_channel, "!mp settings")


bot.run(os.getenv("BOT_TOKEN"))
