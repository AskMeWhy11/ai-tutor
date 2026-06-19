"""Настройки приложения. Читаются из .env через pydantic-settings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # GigaChat
    gigachat_credentials: str = ""
    gigachat_scope: str = "GIGACHAT_API_CORP"
    gigachat_model: str = "GigaChat-2-Pro"
    gigachat_timeout_seconds: float = 30.0
    gigachat_verify_ssl: bool = False
    gigachat_ca_bundle: str = "russian_trusted_root_ca.cer"

    # SaluteSpeech
    salutespeech_api_key: str = ""
    salutespeech_oauth_url: str = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    salutespeech_tts_url: str = "https://smartspeech.sber.ru/rest/v1/text:synthesize"
    salutespeech_stt_url: str = "https://smartspeech.sber.ru/rest/v1/speech:recognize"
    salutespeech_scope: str = "SALUTE_SPEECH_CORP"
    salutespeech_voice: str = "May_24000"
    salutespeech_format: str = "wav16"
    salutespeech_ca_bundle: str = "russian_trusted_root_ca.cer"
    salutespeech_enabled: bool = True

    # Кэш TTS
    tts_cache_dir: str = "var/tts"
    tts_cache_ttl_seconds: float = 2 * 24 * 3600  # 2 дней
    tts_cache_cleanup_interval_seconds: float = 6 * 3600  # 6 часов

    # Промпты
    prompts_path: str = "var/prompts/templates.json"

    # Админка
    admin_username: str = "admin"
    admin_password: str = "admin"

    @property
    def tts_cache_path(self) -> Path:
        return Path(self.tts_cache_dir)

    @property
    def prompts_file(self) -> Path:
        return Path(self.prompts_path)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
