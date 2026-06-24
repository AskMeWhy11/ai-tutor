"""NullTTS всегда возвращает None."""

from __future__ import annotations

import pytest

from infrastructure.tts.null_tts import NullTTS


@pytest.mark.asyncio
async def test_null_tts_returns_none() -> None:
    tts = NullTTS()
    assert await tts.synthesize("любой текст") is None
    assert tts.mime == "audio/wav"
    assert tts.extension == "wav"
