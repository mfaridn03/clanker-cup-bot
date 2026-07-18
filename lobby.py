from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass

import discord

WEBHOOK_RATE = 5
WEBHOOK_WINDOW_S = 2.0
BANCHO_AVATAR_URL = "https://a.ppy.sh/3"


@dataclass(slots=True)
class _QueuedSend:
    content: str
    username: str
    avatar_url: str | None


class RateLimitedWebhook:
    """Queues webhook.send calls and enforces 5 requests per 2 seconds."""

    def __init__(self, webhook: discord.Webhook) -> None:
        self.webhook = webhook
        self._queue: asyncio.Queue[_QueuedSend | None] = asyncio.Queue()
        self._sent_at: deque[float] = deque()
        self._task = asyncio.create_task(self._worker(), name=f"webhook-{webhook.id}")

    def enqueue(
        self,
        content: str,
        *,
        username: str,
        avatar_url: str | None = None,
    ) -> None:
        self._queue.put_nowait(_QueuedSend(content, username, avatar_url))

    def stop(self) -> None:
        self._queue.put_nowait(None)
        self._task.cancel()

    async def _acquire_slot(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            now = loop.time()
            while self._sent_at and now - self._sent_at[0] >= WEBHOOK_WINDOW_S:
                self._sent_at.popleft()
            if len(self._sent_at) < WEBHOOK_RATE:
                self._sent_at.append(now)
                return
            await asyncio.sleep(WEBHOOK_WINDOW_S - (now - self._sent_at[0]))

    async def _worker(self) -> None:
        try:
            while True:
                item = await self._queue.get()
                if item is None:
                    return
                await self._acquire_slot()
                try:
                    kwargs: dict[str, object] = {
                        "content": item.content,
                        "username": item.username,
                        "allowed_mentions": discord.AllowedMentions.none(),
                        "suppress_embeds": True,
                    }
                    if item.avatar_url is not None:
                        kwargs["avatar_url"] = item.avatar_url
                    await self.webhook.send(**kwargs)
                except Exception as exc:
                    print(f"[webhook:{self.webhook.id}] send failed: {exc}")
        except asyncio.CancelledError:
            raise


@dataclass
class Lobby:
    lobby_id: str
    irc_channel: str
    discord_channel_id: int
    owner_id: int
    banchobot_webhook: RateLimitedWebhook
    other_webhook: RateLimitedWebhook

    def enqueue_irc(self, nick: str, message: str) -> None:
        if nick.casefold() == "banchobot":
            self.banchobot_webhook.enqueue(
                message,
                username=nick,
                avatar_url=BANCHO_AVATAR_URL,
            )
        else:
            self.other_webhook.enqueue(message, username=nick)

    def close(self) -> None:
        self.banchobot_webhook.stop()
        self.other_webhook.stop()


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
        lobby.close()

    def remove_by_irc(self, irc_channel: str) -> Lobby | None:
        lobby = self._by_irc.pop(irc_channel.casefold(), None)
        if lobby is None:
            return None
        self._by_discord.pop(lobby.discord_channel_id, None)
        lobby.close()
        return lobby
