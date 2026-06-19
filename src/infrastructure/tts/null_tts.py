"""Заглушка TTS — всегда возвращает None. Используется,
когда SaluteSpeech не настроен или отключён."""

from __future__ import annotations


class NullTTS:
    @property
    def mime(self) -> str:
        return "audio/wav"

    @property
    def extension(self) -> str:
        return "wav"

    async def synthesize(self, text: str) -> bytes | None:
        return None
