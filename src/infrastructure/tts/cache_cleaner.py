"""Фоновая периодическая очистка кэша TTS."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from infrastructure.tts.audio_cache import FileAudioCache

logger = logging.getLogger(__name__)

__all__ = ["AudioCacheCleaner"]


class AudioCacheCleaner:
    def __init__(
        self,
        cache: FileAudioCache,
        *,
        ttl_seconds: float,
        interval_seconds: float,
    ) -> None:
        self._cache = cache
        self._ttl = ttl_seconds
        self._interval = interval_seconds
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._ttl <= 0 or self._interval <= 0:
            logger.info(
                "AudioCacheCleaner отключён (ttl=%s, interval=%s)", self._ttl, self._interval
            )
            return
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run(), name="audio-cache-cleaner")
        logger.info(
            "AudioCacheCleaner запущен: ttl=%.0fс, interval=%.0fс",
            self._ttl,
            self._interval,
        )

    async def stop(self) -> None:
        task = self._task
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
        self._task = None

    async def _run(self) -> None:
        try:
            # Первый прогон сразу — чтобы освободить место на старте.
            await self._safe_purge()
            while True:
                await asyncio.sleep(self._interval)
                await self._safe_purge()
        except asyncio.CancelledError:
            raise

    async def _safe_purge(self) -> None:
        try:
            await self._cache.purge_older_than(self._ttl)
        except Exception:
            logger.exception("AudioCacheCleaner: ошибка очистки")
