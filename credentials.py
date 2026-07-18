from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict

import aiofiles

DATA_DIR = Path("data/users")


class Credentials(TypedDict):
    nick: str
    password: str


def _path_for(user_id: int) -> Path:
    return DATA_DIR / f"{user_id}.json"


async def load(user_id: int) -> Credentials | None:
    path = _path_for(user_id)
    if not path.is_file():
        return None
    async with aiofiles.open(path, encoding="utf-8") as f:
        raw = await f.read()
    data = json.loads(raw)
    nick = data.get("nick")
    password = data.get("password")
    if not isinstance(nick, str) or not isinstance(password, str):
        return None
    if not nick or not password:
        return None
    return Credentials(nick=nick, password=password)


# yes it's in plaintext since data/ is gitignored anyway. just dont get hacked
async def save(user_id: int, nick: str, password: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"nick": nick, "password": password}, indent=2)
    async with aiofiles.open(_path_for(user_id), "w", encoding="utf-8") as f:
        await f.write(payload)
