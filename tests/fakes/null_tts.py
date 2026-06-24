"""TTS-заглушка для тестов: всегда None, не делает сетевых вызовов."""

from __future__ import annotations


class FakeNullTTS:
    @property
    def mime(self) -> str:
        return "audio/wav"

    @property
    def extension(self) -> str:
        return "wav"

    async def synthesize(self, text: str) -> bytes | None:
        return None
