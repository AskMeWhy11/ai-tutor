"""Клиент SaluteSpeech TTS.

OAuth: POST {oauth_url} с Authorization: Basic <api_key> и
RqUID (UUID4). Возвращает access_token + expires_at (epoch ms).
Токен кэшируется в памяти.

Синтез: POST {tts_url}?format=...&voice=... с Content-Type: application/text
(тело — сырой текст). Возвращает аудио в выбранном формате.

Ошибки: на любом исключении возвращает None — runner просто не эмитит
PlayAudio, текст всё равно показывается.
"""

from __future__ import annotations

import asyncio
import logging
import time
from uuid import uuid4

import httpx

logger = logging.getLogger(__name__)

__all__ = ["SaluteSpeechTTS"]


class SaluteSpeechTTS:
    def __init__(
        self,
        api_key: str,
        oauth_url: str,
        tts_url: str,
        scope: str,
        voice: str,
        audio_format: str,
        verify: str | bool,
    ) -> None:
        self._api_key = api_key
        self._oauth_url = oauth_url
        self._tts_url = tts_url
        self._scope = scope
        self._voice = voice
        self._format = audio_format
        self._verify = verify

        self._token: str | None = None
        self._token_exp: float = 0.0
        self._lock = asyncio.Lock()

    @property
    def mime(self) -> str:
        # wav16 → audio/wav; opus → audio/ogg; pcm16 → audio/wav (как контейнер).
        if self._format.startswith("opus"):
            return "audio/ogg"
        if self._format.startswith("mp3"):
            return "audio/mpeg"
        return "audio/wav"

    @property
    def extension(self) -> str:
        if self._format.startswith("opus"):
            return "ogg"
        if self._format.startswith("mp3"):
            return "mp3"
        return "wav"

    async def synthesize(self, text: str) -> bytes | None:
        if not text.strip() or not self._api_key:
            return None
        try:
            token = await self._get_token()
        except Exception:
            logger.exception("SaluteSpeech: failed to obtain access token")
            return None

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/text",
        }
        params = {"format": self._format, "voice": self._voice}
        try:
            async with httpx.AsyncClient(verify=self._verify, timeout=30.0) as client:
                resp = await client.post(
                    self._tts_url,
                    params=params,
                    headers=headers,
                    content=text.encode("utf-8"),
                )
                resp.raise_for_status()
                return resp.content
        except Exception:
            logger.exception("SaluteSpeech: synthesis failed")
            return None

    async def _get_token(self) -> str:
        now = time.time()
        if self._token and now < self._token_exp - 30:
            return self._token

        async with self._lock:
            now = time.time()
            if self._token and now < self._token_exp - 30:
                return self._token

            headers = {
                "Authorization": f"Basic {self._api_key}",
                "RqUID": str(uuid4()),
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            }
            data = {"scope": self._scope}
            async with httpx.AsyncClient(verify=self._verify, timeout=30.0) as client:
                resp = await client.post(self._oauth_url, headers=headers, data=data)
                resp.raise_for_status()
                payload = resp.json()
            self._token = str(payload["access_token"])
            # expires_at — epoch ms
            exp_ms = float(payload.get("expires_at", 0))
            self._token_exp = exp_ms / 1000.0 if exp_ms else now + 1500
            return self._token
