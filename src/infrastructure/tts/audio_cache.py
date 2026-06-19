"""Файловый кэш аудио по sha256(bytes)."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = ["FileAudioCache"]


class FileAudioCache:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    async def put(self, audio: bytes, ext: str) -> str:
        digest = hashlib.sha256(audio).hexdigest()
        name = f"{digest}.{ext}"
        path = self._root / name
        if not path.exists():
            await asyncio.to_thread(path.write_bytes, audio)
        return name

    def path_for(self, key: str) -> Path | None:
        # Защита от path traversal: только имя файла без сепараторов.
        if "/" in key or "\\" in key or ".." in key:
            return None
        path = self._root / key
        if not path.exists():
            return None
        return path

    async def purge_older_than(self, ttl_seconds: float) -> int:
        """Удалить файлы старше ttl_seconds (по mtime). Возвращает число удалённых."""
        if ttl_seconds <= 0:
            return 0
        return await asyncio.to_thread(self._purge_sync, ttl_seconds)

    def _purge_sync(self, ttl_seconds: float) -> int:
        cutoff = time.time() - ttl_seconds
        removed = 0
        try:
            entries = list(self._root.iterdir())
        except OSError:
            logger.exception("audio_cache: не удалось прочитать %s", self._root)
            return 0
        for entry in entries:
            try:
                if not entry.is_file():
                    continue
                if entry.stat().st_mtime < cutoff:
                    entry.unlink()
                    removed += 1
            except OSError:
                logger.exception("audio_cache: не удалось удалить %s", entry)
        if removed:
            logger.info("audio_cache: удалено %d файлов старше %.0f с", removed, ttl_seconds)
        return removed
