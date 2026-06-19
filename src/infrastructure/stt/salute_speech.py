"""SaluteSpeech STT.

OAuth идентичен TTS (Basic API key + RqUID → access_token).
Распознавание: POST {stt_url}?language=ru-RU с Content-Type аудио, тело — bytes.
Ответ: {"status":200,"result":["распознанный текст", ...]}.

TODO: вынести OAuth в общий salute_auth.py — сейчас дублируется с TTS.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any
from uuid import uuid4

import httpx

logger = logging.getLogger(__name__)

__all__ = ["SaluteSpeechSTT"]


class SaluteSpeechSTT:
    def __init__(
        self,
        api_key: str,
        oauth_url: str,
        stt_url: str,
        scope: str,
        verify: str | bool,
    ) -> None:
        self._api_key = api_key
        self._oauth_url = oauth_url
        self._stt_url = stt_url
        self._scope = scope
        self._verify = verify

        self._token: str | None = None
        self._token_exp: float = 0.0
        self._lock = asyncio.Lock()

    @property
    def available(self) -> bool:
        return bool(self._api_key)

    async def recognize(self, audio: bytes, mime: str) -> str | None:
        if not audio or not self._api_key:
            return None
        try:
            token = await self._get_token()
        except Exception:
            logger.exception("SaluteSpeech STT: failed to get token")
            return None

        content_type = self._normalize_mime(mime)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": content_type,
        }
        params = {"language": "ru-RU"}
        logger.info(
            "STT request: in_mime=%r → out_ct=%r bytes=%d",
            mime,
            content_type,
            len(audio),
        )
        try:
            async with httpx.AsyncClient(verify=self._verify, timeout=60.0) as client:
                resp = await client.post(
                    self._stt_url,
                    params=params,
                    headers=headers,
                    content=audio,
                )
                if resp.status_code >= 400:
                    logger.error(
                        "SaluteSpeech STT HTTP %s: %s",
                        resp.status_code,
                        resp.text[:500],
                    )
                    return None
                payload: dict[str, Any] = resp.json()
        except Exception:
            logger.exception("SaluteSpeech STT: recognition failed")
            return None

        logger.info("STT response payload: %r", payload)
        results = payload.get("result") or []
        if not isinstance(results, list) or not results:
            return None
        text = " ".join(str(x).strip() for x in results if x).strip()
        return text or None

    @staticmethod
    def _normalize_mime(mime: str) -> str:
        m = (mime or "").lower()
        if "wav" in m or "x-wav" in m or "pcm" in m:
            return "audio/x-pcm;bit=16;rate=16000"
        if "opus" in m and "ogg" in m:
            return "audio/ogg;codecs=opus"
        if "ogg" in m:
            return "audio/ogg;codecs=opus"
        if "mpeg" in m or "mp3" in m:
            return "audio/mpeg"
        if "flac" in m:
            return "audio/flac"
        # WebM/Opus сюда не годится — это уже отбраковано выше.
        return "audio/ogg;codecs=opus"

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
            exp_ms = float(payload.get("expires_at", 0))
            self._token_exp = exp_ms / 1000.0 if exp_ms else now + 1500
            return self._token
