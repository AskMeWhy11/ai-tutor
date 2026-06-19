"""STT-заглушка. Возвращает None, available=False."""

from __future__ import annotations


class NullSTT:
    @property
    def available(self) -> bool:
        return False

    async def recognize(self, audio: bytes, mime: str) -> str | None:
        return None
