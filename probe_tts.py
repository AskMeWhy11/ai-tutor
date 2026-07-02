"""Диагностика SaluteSpeech TTS. Запуск: python probe_tts.py"""

from __future__ import annotations

import asyncio
import logging
import sys

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")

from infrastructure.config import get_settings  # noqa: E402


async def main() -> int:
    s = get_settings()
    print("enabled =", s.salutespeech_enabled)
    print("key_set =", bool(s.salutespeech_api_key.strip()))
    print("oauth   =", s.salutespeech_oauth_url)
    print("tts_url =", s.salutespeech_tts_url)
    print("scope   =", s.salutespeech_scope)
    print("voice   =", s.salutespeech_voice)
    print("format  =", s.salutespeech_format)
    print("ca      =", s.salutespeech_ca_bundle)

    if not s.salutespeech_api_key.strip():
        print("!! api_key пуст — TTS отключён на уровне composition")
        return 1

    import httpx

    from infrastructure.tts.salute_speech import SaluteSpeechTTS

    ca = s.salutespeech_ca_bundle.strip()
    verify: str | bool = ca if ca else True

    # --- OAuth напрямую, с телом ответа при ошибке ---
    from uuid import uuid4

    async with httpx.AsyncClient(verify=verify, timeout=30.0) as c:
        try:
            r = await c.post(
                s.salutespeech_oauth_url,
                headers={
                    "Authorization": f"Basic {s.salutespeech_api_key}",
                    "RqUID": str(uuid4()),
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
                data={"scope": s.salutespeech_scope},
            )
            print("OAUTH status:", r.status_code)
            if r.status_code != 200:
                print("OAUTH body:", r.text[:500])
                return 2
        except Exception as e:
            print("OAUTH EXC:", type(e).__name__, e)
            return 2

    # --- Синтез через боевой клиент ---
    tts = SaluteSpeechTTS(
        api_key=s.salutespeech_api_key,
        oauth_url=s.salutespeech_oauth_url,
        tts_url=s.salutespeech_tts_url,
        scope=s.salutespeech_scope,
        voice=s.salutespeech_voice,
        audio_format=s.salutespeech_format,
        verify=verify,
    )
    audio = await tts.synthesize("Проверка синтеза речи. Раз, два, три.")
    if audio is None:
        print("!! synthesize вернул None — смотри лог выше (synthesis failed)")
        return 3

    out = f"probe_out.{tts.extension}"
    with open(out, "wb") as f:
        f.write(audio)
    print(f"OK: {len(audio)} байт → {out} (mime={tts.mime})")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
