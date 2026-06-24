import os
import time

import pytest

from infrastructure.tts.audio_cache import FileAudioCache


@pytest.mark.asyncio
async def test_purge_older_than_removes_stale(tmp_path):
    cache = FileAudioCache(tmp_path)
    old_name = await cache.put(b"old", "wav")
    new_name = await cache.put(b"new", "wav")

    old_path = tmp_path / old_name
    stale = time.time() - 1000
    os.utime(old_path, (stale, stale))

    removed = await cache.purge_older_than(ttl_seconds=500)
    assert removed == 1
    assert not old_path.exists()
    assert (tmp_path / new_name).exists()


@pytest.mark.asyncio
async def test_purge_older_than_noop_when_disabled(tmp_path):
    cache = FileAudioCache(tmp_path)
    await cache.put(b"x", "wav")
    assert await cache.purge_older_than(ttl_seconds=0) == 0
    assert len(list(tmp_path.iterdir())) == 1
