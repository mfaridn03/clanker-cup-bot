from __future__ import annotations

from irc.session import IrcSession, OnPart, OnPrivmsg


class SessionManager:
    """Tracks concurrent IRC sessions keyed by Discord user id."""

    def __init__(
        self,
        *,
        on_privmsg: OnPrivmsg | None = None,
        on_part: OnPart | None = None,
    ) -> None:
        self._sessions: dict[int, IrcSession] = {}
        self._on_privmsg = on_privmsg
        self._on_part = on_part

    def get(self, user_id: int) -> IrcSession | None:
        return self._sessions.get(user_id)

    def __len__(self) -> int:
        return len(self._sessions)

    async def connect(self, user_id: int, nick: str, password: str) -> IrcSession:
        if user_id in self._sessions:
            raise RuntimeError("already connected")

        session = IrcSession(
            user_id,
            nick,
            password,
            on_stopped=self._on_session_stopped,
            on_privmsg=self._on_privmsg,
            on_part=self._on_part,
        )
        self._sessions[user_id] = session
        try:
            await session.start()
        except Exception:
            self._sessions.pop(user_id, None)
            raise
        return session

    async def disconnect(self, user_id: int) -> bool:
        session = self._sessions.pop(user_id, None)
        if session is None:
            return False
        await session.stop()
        return True

    async def disconnect_all(self) -> None:
        user_ids = list(self._sessions.keys())
        for user_id in user_ids:
            await self.disconnect(user_id)

    async def _on_session_stopped(self, user_id: int) -> None:
        self._sessions.pop(user_id, None)
