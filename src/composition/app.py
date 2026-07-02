"""Composition root: сборка FastAPI-приложения и зависимостей."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request as _StReq

from application.fsm_service import FSMService
from application.ports.answer_checker import AnswerChecker
from application.ports.avatar import AvatarClient
from application.ports.practice_evaluator import PracticeEvaluator
from application.ports.quiz_director import QuizDirector
from application.ports.session_store import SessionStore
from application.ports.stage_director import StageDirector
from application.ports.stt_client import STTClient
from application.ports.tts_client import TTSClient
from application.session_runner import SessionRunner
from infrastructure.config import Settings, get_settings
from infrastructure.llm.prompt_store import PromptStore
from infrastructure.llm.stub_avatar import StubAvatar
from infrastructure.llm.stub_checker import StubAnswerChecker
from infrastructure.llm.stub_practice_evaluator import StubPracticeEvaluator
from infrastructure.llm.stub_quiz_director import StubQuizDirector
from infrastructure.llm.stub_stage_director import StubStageDirector
from infrastructure.persistence.in_memory_session_store import InMemorySessionStore
from infrastructure.stt.null_stt import NullSTT
from infrastructure.stt.salute_speech import SaluteSpeechSTT
from infrastructure.tts.audio_cache import FileAudioCache
from infrastructure.tts.cache_cleaner import AudioCacheCleaner
from infrastructure.tts.null_tts import NullTTS
from infrastructure.tts.salute_speech import SaluteSpeechTTS
from infrastructure.web.routes_admin import build_admin_router
from infrastructure.web.routes_api import build_api_router
from infrastructure.web.routes_ui import build_ui_router
from infrastructure.web.security import LoginRedirect

if TYPE_CHECKING:
    from gigachat import GigaChat

logger = logging.getLogger(__name__)

_WEB_DIR = Path(__file__).resolve().parent.parent / "infrastructure" / "web"
_STATIC_DIR = _WEB_DIR / "static"
_TEMPLATES_DIR = _WEB_DIR / "templates"


def create_app(
    settings: Settings | None = None,
    *,
    store: SessionStore | None = None,
    tts: TTSClient | None = None,
    stt: STTClient | None = None,
    avatar: AvatarClient | None = None,
    answer_checker: AnswerChecker | None = None,
    practice_evaluator: PracticeEvaluator | None = None,
    quiz_director: QuizDirector | None = None,
    stage_director: StageDirector | None = None,
) -> FastAPI:
    settings = settings or get_settings()

    audio_cache = FileAudioCache(settings.tts_cache_path)
    cache_cleaner = AudioCacheCleaner(
        audio_cache,
        ttl_seconds=settings.tts_cache_ttl_seconds,
        interval_seconds=settings.tts_cache_cleanup_interval_seconds,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        cache_cleaner.start()
        try:
            yield
        finally:
            await cache_cleaner.stop()

    app = FastAPI(title="AI-наставник", version="0.1.0", lifespan=lifespan)

    @app.exception_handler(LoginRedirect)
    async def _login_redirect_handler(_req: _StReq, exc: LoginRedirect) -> Any:
        return exc.response

    fsm = FSMService()
    session_store = store or InMemorySessionStore()
    prompt_store = PromptStore(settings.prompts_file)

    gigachat_client = _try_build_gigachat(settings)

    avatar_client = avatar or _build_avatar(settings, prompt_store, gigachat_client)
    tts_client = tts or _build_tts(settings)
    stt_client = stt or _build_stt(settings)

    checker = answer_checker or _build_answer_checker(settings, gigachat_client)
    evaluator = practice_evaluator or _build_practice_evaluator(settings, gigachat_client)
    director = quiz_director or _build_quiz_director(settings, prompt_store, gigachat_client)
    stage = stage_director or _build_stage_director(settings, prompt_store, gigachat_client)

    runner = SessionRunner(
        fsm=fsm,
        store=session_store,
        avatar=avatar_client,
        tts=tts_client,
        audio_cache=audio_cache,
        answer_checker=checker,
        practice_evaluator=evaluator,
        quiz_director=director,
        stage_director=stage,
    )

    app.state.settings = settings
    app.state.store = session_store
    app.state.runner = runner
    app.state.audio_cache = audio_cache
    app.state.prompt_store = prompt_store
    app.state.stt = stt_client
    app.state.templates = Jinja2Templates(directory=_TEMPLATES_DIR)

    app.include_router(build_ui_router())
    app.include_router(build_api_router(), prefix="/api")
    for admin_router in build_admin_router():
        app.include_router(admin_router)

    if _STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    return app


def _try_build_gigachat(settings: Settings) -> GigaChat | None:
    creds = settings.gigachat_credentials.strip()
    if not creds:
        return None
    try:
        from gigachat import GigaChat
    except Exception:
        logger.exception("gigachat SDK недоступен")
        return None

    verify_ssl_certs: bool = bool(settings.gigachat_verify_ssl)
    ca_bundle_file: str | None = None
    if settings.gigachat_verify_ssl:
        ca = settings.gigachat_ca_bundle.strip()
        ca_bundle_file = ca or None

    try:
        kwargs: dict[str, Any] = {
            "credentials": creds,
            "scope": settings.gigachat_scope,
            "model": settings.gigachat_model,
            "verify_ssl_certs": verify_ssl_certs,
            "timeout": settings.gigachat_timeout_seconds,
        }
        if ca_bundle_file is not None:
            kwargs["ca_bundle_file"] = ca_bundle_file
        return GigaChat(**kwargs)
    except Exception:
        logger.exception("Не удалось инициализировать GigaChat")
        return None


def _build_avatar(
    settings: Settings,
    prompt_store: PromptStore,
    client: GigaChat | None,
) -> AvatarClient:
    stub = StubAvatar(prompt_store)
    if client is None:
        logger.info("GIGACHAT не настроен — используется StubAvatar")
        return stub
    try:
        from infrastructure.llm.gigachat_avatar import GigaChatAvatar
    except Exception:
        logger.exception("GigaChatAvatar import failed — fallback на StubAvatar")
        return stub
    logger.info("GigaChatAvatar активирован (model=%s)", settings.gigachat_model)
    return GigaChatAvatar(
        client=client,
        prompt_store=prompt_store,
        fallback=stub,
        model=settings.gigachat_model,
        timeout=settings.gigachat_timeout_seconds,
    )


def _build_answer_checker(settings: Settings, client: GigaChat | None) -> AnswerChecker:
    stub = StubAnswerChecker()
    if client is None:
        return stub
    try:
        from infrastructure.llm.gigachat_answer_checker import GigaChatAnswerChecker
    except Exception:
        logger.exception("GigaChatAnswerChecker import failed — fallback на stub")
        return stub
    return GigaChatAnswerChecker(client=client, fallback=stub, model=settings.gigachat_model)


def _build_practice_evaluator(settings: Settings, client: GigaChat | None) -> PracticeEvaluator:
    stub = StubPracticeEvaluator()
    if client is None:
        return stub
    try:
        from infrastructure.llm.gigachat_practice_evaluator import (
            GigaChatPracticeEvaluator,
        )
    except Exception:
        logger.exception("GigaChatPracticeEvaluator import failed — fallback на stub")
        return stub
    return GigaChatPracticeEvaluator(client=client, fallback=stub, model=settings.gigachat_model)


def _build_quiz_director(
    settings: Settings,
    prompt_store: PromptStore,
    client: GigaChat | None,
) -> QuizDirector:
    stub = StubQuizDirector()
    if client is None:
        logger.info("GIGACHAT не настроен — используется StubQuizDirector")
        return stub
    try:
        from infrastructure.llm.gigachat_quiz_director import GigaChatQuizDirector
    except Exception:
        logger.exception("GigaChatQuizDirector import failed — fallback на stub")
        return stub
    logger.info("GigaChatQuizDirector активирован")
    return GigaChatQuizDirector(
        client=client,
        prompt_store=prompt_store,
        fallback=stub,
        model=settings.gigachat_model,
    )


def _build_stage_director(
    settings: Settings,
    prompt_store: PromptStore,
    client: GigaChat | None,
) -> StageDirector:
    stub = StubStageDirector()
    if client is None:
        logger.info("GIGACHAT не настроен — используется StubStageDirector")
        return stub
    try:
        from infrastructure.llm.gigachat_stage_director import GigaChatStageDirector
    except Exception:
        logger.exception("GigaChatStageDirector import failed — fallback на stub")
        return stub
    logger.info("GigaChatStageDirector активирован")
    return GigaChatStageDirector(
        client=client,
        prompt_store=prompt_store,
        fallback=stub,
        model=settings.gigachat_model,
    )


def _build_tts(settings: Settings) -> TTSClient:
    if not settings.salutespeech_enabled or not settings.salutespeech_api_key.strip():
        logger.info("SaluteSpeech TTS отключён — используется NullTTS")
        return NullTTS()
    ca = settings.salutespeech_ca_bundle.strip()
    verify: str | bool = ca if ca else True
    return SaluteSpeechTTS(
        api_key=settings.salutespeech_api_key,
        oauth_url=settings.salutespeech_oauth_url,
        tts_url=settings.salutespeech_tts_url,
        scope=settings.salutespeech_scope,
        voice=settings.salutespeech_voice,
        audio_format=settings.salutespeech_format,
        verify=verify,
    )


def _build_stt(settings: Settings) -> STTClient:
    if not settings.salutespeech_enabled or not settings.salutespeech_api_key.strip():
        logger.info("SaluteSpeech STT отключён — используется NullSTT")
        return NullSTT()
    ca = settings.salutespeech_ca_bundle.strip()
    verify: str | bool = ca if ca else True
    return SaluteSpeechSTT(
        api_key=settings.salutespeech_api_key,
        oauth_url=settings.salutespeech_oauth_url,
        stt_url=settings.salutespeech_stt_url,
        scope=settings.salutespeech_scope,
        verify=verify,
    )
