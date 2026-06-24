import asyncio
import os
import time

import pytest

from infrastructure.tts.audio_cache import FileAudioCache
from infrastructure.tts.cache_cleaner import AudioCacheCleaner


@pytest.mark.asyncio
async def test_cleaner_runs_initial_purge(tmp_path):
    cache = FileAudioCache(tmp_path)
    name = await cache.put(b"old", "wav")
    path = tmp_path / name
    stale = time.time() - 10_000
    os.utime(path, (stale, stale))

    cleaner = AudioCacheCleaner(cache, ttl_seconds=100, interval_seconds=3600)
    cleaner.start()
    # Дать таску выполнить первый прогон.
    await asyncio.sleep(0.05)
    await cleaner.stop()

    assert not path.exists()


@pytest.mark.asyncio
async def test_cleaner_disabled_when_ttl_zero(tmp_path):
    cache = FileAudioCache(tmp_path)
    name = await cache.put(b"x", "wav")

    cleaner = AudioCacheCleaner(cache, ttl_seconds=0, interval_seconds=3600)
    cleaner.start()
    await asyncio.sleep(0.05)
    await cleaner.stop()

    assert (tmp_path / name).exists()
