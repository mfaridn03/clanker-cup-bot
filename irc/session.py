from __future__ import annotations

import asyncio
from collections.abc import Callable, Awaitable

import bottom

BANCHO_HOST = "irc.ppy.sh"
BANCHO_PORT = 6667

OnStopped = Callable[[int], Awaitable[None] | None]


class IrcSession:
    """One Discord user's IRC connection to osu! Bancho."""

    def __init__(
        self,
        user_id: int,
        nick: str,
        password: str,
        *,
        on_stopped: OnStopped | None = None,
    ) -> None:
        self.user_id = user_id
        self.nick = nick.replace(" ", "_")
        self.password = password
        self._on_stopped = on_stopped
        self._client = bottom.Client(host=BANCHO_HOST, port=BANCHO_PORT, ssl=False)
        self._task: asyncio.Task[None] | None = None
        self._stopping = False
        self._register_handlers()

    def _register_handlers(self) -> None:
        client = self._client

        @client.on("CLIENT_CONNECT")
        async def on_connect(**_kwargs: object) -> None:
            await client.send("pass", password=self.password)
            await client.send("nick", nick=self.nick)
            await client.send("user", nick=self.nick, realname=self.nick)
            print(f"[irc:{self.user_id}] connected as {self.nick}")

        @client.on("PRIVMSG")
        async def on_privmsg(nick: str, target: str, message: str, **_kwargs: object) -> None:
            print(f"[irc:{self.user_id}] <{nick}> {target}: {message}")

        @client.on("NOTICE")
        async def on_notice(nick: str | None = None, target: str | None = None, message: str = "", **_kwargs: object) -> None:
            sender = nick or "server"
            print(f"[irc:{self.user_id}] -{sender}- {target}: {message}")

        @client.on("JOIN")
        async def on_join(**_kwargs: object) -> None:
            return

        @client.on("PART")
        async def on_part(**_kwargs: object) -> None:
            return

        @client.on("CLIENT_DISCONNECT")
        async def on_disconnect(**_kwargs: object) -> None:
            print(f"[irc:{self.user_id}] disconnected")
            if not self._stopping and self._on_stopped is not None:
                result = self._on_stopped(self.user_id)
                if asyncio.iscoroutine(result):
                    await result

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            raise RuntimeError("session already started")
        self._stopping = False
        self._task = asyncio.create_task(self._run(), name=f"irc-{self.user_id}")

    async def _run(self) -> None:
        try:
            await self._client.connect()
            await self._client.wait("client_disconnect")
        except asyncio.CancelledError:
            await self._client.disconnect()
            raise
        except Exception as exc:
            print(f"[irc:{self.user_id}] error: {exc}")
            await self._client.disconnect()

    async def stop(self) -> None:
        self._stopping = True
        await self._client.disconnect()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
