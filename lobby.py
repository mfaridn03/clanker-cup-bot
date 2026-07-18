from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Lobby:
    lobby_id: str
    irc_channel: str
    discord_channel_id: int
    owner_id: int


class LobbyManager:
    """Maps Discord lobby channels to Bancho #mp_* IRC channels."""

    def __init__(self) -> None:
        self._by_discord: dict[int, Lobby] = {}
        self._by_irc: dict[str, Lobby] = {}

    def add(self, lobby: Lobby) -> None:
        self._by_discord[lobby.discord_channel_id] = lobby
        self._by_irc[lobby.irc_channel.casefold()] = lobby

    def get_by_discord(self, channel_id: int) -> Lobby | None:
        return self._by_discord.get(channel_id)

    def get_by_irc(self, irc_channel: str) -> Lobby | None:
        return self._by_irc.get(irc_channel.casefold())

    def remove(self, lobby: Lobby) -> None:
        self._by_discord.pop(lobby.discord_channel_id, None)
        self._by_irc.pop(lobby.irc_channel.casefold(), None)
