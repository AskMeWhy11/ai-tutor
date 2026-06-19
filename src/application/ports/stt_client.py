"""Порт распознавания речи."""

from __future__ import annotations

from typing import Protocol


class STTClient(Protocol):
    async def recognize(self, audio: bytes, mime: str) -> str | None:
        """Распознать аудио. None = STT недоступен (нет ключей/ошибка сети)."""
        ...

    @property
    def available(self) -> bool:
        """True, если STT можно использовать (есть креды и не отключен)."""
        ...
