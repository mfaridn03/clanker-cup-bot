import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())

ALLOWED_SERVER = 1527856371884884048
STAFF_ROLE = 1527871437489045514

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")


@bot.tree.command(name="ping", description="pong!")
async def ping(ctx: discord.Interaction):
    await ctx.response.send_message("pong!", ephemeral=True)

@bot.tree.command(name="register")
async def register(ctx: discord.Interaction, nick: str, irc_password: str):
    if STAFF_ROLE not in [role.id for role in ctx.user.roles] or ctx.guild_id != ALLOWED_SERVER:
        return # nuh uh
    
    await ctx.response.send_message("register cmd", ephemeral=True)

@bot.tree.command(name="connect", description="connect to irc")
async def connect(ctx: discord.Interaction):
    if STAFF_ROLE not in [role.id for role in ctx.user.roles] or ctx.guild_id != ALLOWED_SERVER:
        return

    await ctx.response.send_message("cnnect cmd", ephemeral=True)


bot.run(os.getenv("BOT_TOKEN"))
