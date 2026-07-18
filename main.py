from enum import member
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())


@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")


@bot.tree.command(name="ping", description="pong!")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("pong!", ephemeral=True)


bot.run(os.getenv("BOT_TOKEN"))
