from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import bottom

BANCHO_HOST = "irc.ppy.sh"
BANCHO_PORT = 6667
PING_INTERVAL_S = 60

OnStopped = Callable[[int], Awaitable[None] | None]
OnPrivmsg = Callable[[str, str, str], Awaitable[None] | None]
PrivmsgPredicate = Callable[[str, str, str], bool]


class IrcSession:
    """One Discord user's IRC connection to osu! Bancho."""

    def __init__(
        self,
        user_id: int,
        nick: str,
        password: str,
        *,
        on_stopped: OnStopped | None = None,
        on_privmsg: OnPrivmsg | None = None,
    ) -> None:
        self.user_id = user_id
        self.nick = nick.replace(" ", "_")
        self.password = password
        self._on_stopped = on_stopped
        self._on_privmsg = on_privmsg
        self._client = bottom.Client(host=BANCHO_HOST, port=BANCHO_PORT, ssl=False)
        self._task: asyncio.Task[None] | None = None
        self._ping_task: asyncio.Task[None] | None = None
        self._stopping = False
        self._privmsg_waiters: list[tuple[PrivmsgPredicate, asyncio.Future[tuple[str, str, str]]]] = []
        self._register_handlers()

    def _register_handlers(self) -> None:
        client = self._client

        @client.on("CLIENT_CONNECT")
        async def on_connect(**_kwargs: object) -> None:
            await client.send("pass", password=self.password)
            await client.send("nick", nick=self.nick)
            await client.send("user", nick=self.nick, realname=self.nick)
            self._start_keepalive()
            print(f"[irc:{self.user_id}] connected as {self.nick}")

        @client.on("PRIVMSG")
        async def on_privmsg(nick: str, target: str, message: str, **_kwargs: object) -> None:
            print(f"[irc:{self.user_id}] <{nick}> {target}: {message}")
            self._resolve_privmsg_waiters(nick, target, message)
            if self._on_privmsg is not None:
                result = self._on_privmsg(nick, target, message)
                if asyncio.iscoroutine(result):
                    await result

        @client.on("NOTICE")
        async def on_notice(nick: str | None = None, target: str | None = None, message: str = "", **_kwargs: object) -> None:
            sender = nick or "server"
            print(f"[irc:{self.user_id}] -{sender}- {target}: {message}")

        @client.on("TOPIC")
        async def on_topic(channel: str | None = None, message: str = "", **_kwargs: object) -> None:
            print(f"[irc:{self.user_id}] TOPIC {channel}: {message}")

        @client.on("RPL_TOPIC")
        async def on_rpl_topic(channel: str | None = None, message: str = "", **_kwargs: object) -> None:
            print(f"[irc:{self.user_id}] RPL_TOPIC {channel}: {message}")

        @client.on("JOIN")
        async def on_join(**_kwargs: object) -> None:
            return

        @client.on("PART")
        async def on_part(**_kwargs: object) -> None:
            return

        @client.on("CLIENT_DISCONNECT")
        async def on_disconnect(**_kwargs: object) -> None:
            self._stop_keepalive()
            self._cancel_privmsg_waiters()
            print(f"[irc:{self.user_id}] disconnected")
            if not self._stopping and self._on_stopped is not None:
                result = self._on_stopped(self.user_id)
                if asyncio.iscoroutine(result):
                    await result

    def _resolve_privmsg_waiters(self, nick: str, target: str, message: str) -> None:
        remaining: list[tuple[PrivmsgPredicate, asyncio.Future[tuple[str, str, str]]]] = []
        for predicate, future in self._privmsg_waiters:
            if future.done():
                continue
            if predicate(nick, target, message):
                future.set_result((nick, target, message))
            else:
                remaining.append((predicate, future))
        self._privmsg_waiters = remaining

    def _cancel_privmsg_waiters(self) -> None:
        for _, future in self._privmsg_waiters:
            if not future.done():
                future.cancel()
        self._privmsg_waiters.clear()

    async def send_privmsg(self, target: str, message: str) -> None:
        await self._client.send("privmsg", target=target, message=message)

    async def wait_privmsg(
        self,
        predicate: PrivmsgPredicate,
        *,
        timeout: float = 15.0,
    ) -> tuple[str, str, str]:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[tuple[str, str, str]] = loop.create_future()
        self._privmsg_waiters.append((predicate, future))
        try:
            return await asyncio.wait_for(future, timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            if not future.done():
                future.cancel()
            self._privmsg_waiters = [(p, f) for p, f in self._privmsg_waiters if f is not future]
            raise

    def _start_keepalive(self) -> None:
        self._stop_keepalive()
        self._ping_task = asyncio.create_task(
            self._keepalive(),
            name=f"irc-ping-{self.user_id}",
        )

    def _stop_keepalive(self) -> None:
        if self._ping_task is None:
            return
        self._ping_task.cancel()
        self._ping_task = None

    async def _keepalive(self) -> None:
        try:
            while True:
                await asyncio.sleep(PING_INTERVAL_S)
                await self._client.send("ping", message=self.nick)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[irc:{self.user_id}] ping error: {exc}")

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
        finally:
            self._stop_keepalive()

    async def stop(self) -> None:
        self._stopping = True
        self._stop_keepalive()
        self._cancel_privmsg_waiters()
        await self._client.disconnect()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
