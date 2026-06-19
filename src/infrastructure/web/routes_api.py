"""HTTP API для FSM-сессий и аудио."""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse

# from starlette.datastructures import UploadFile  # ← базовый класс
from application.commands import (
    Command,
    ConfirmSkipWarning,
    SelectMode,
    StartSession,
    StartTraining,
)
from application.ports.session_store import SessionSnapshot, SessionStore
from application.ports.stt_client import STTClient
from application.session_runner import SessionRunner
from domain.context import SessionContext
from domain.states import FSMState
from infrastructure.tts.audio_cache import FileAudioCache
from infrastructure.web.command_mapper import to_domain_command
from infrastructure.web.schemas import (
    CommandRequest,
    CreateSessionRequest,
    CreateSessionResponse,
    SessionOut,
)
from infrastructure.web.serializers import serialize_result, serialize_session


def build_api_router() -> APIRouter:
    router = APIRouter(tags=["sessions"])

    @router.post(
        "/sessions",
        response_model=CreateSessionResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_session(
        request: Request,
        body: CreateSessionRequest | None = None,
    ) -> CreateSessionResponse:
        store: SessionStore = request.app.state.store
        runner: SessionRunner = request.app.state.runner

        session_id = uuid4()
        await store.save(session_id, FSMState.INIT, SessionContext())

        # INIT → MENU.
        try:
            result = await runner.dispatch(session_id, StartSession())
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

        initial_mode = body.initial_mode if body else None
        if body is not None:
            try:
                result = await runner.dispatch(
                    session_id,
                    StartTraining(
                        employee_name=body.employee_name,
                        product_id=body.product_id,
                    ),
                )
            except ValueError as exc:
                raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

        # Legacy fast-path: доезжаем до выбранного режима.
        if initial_mode is not None:
            fast_path: list[Command] = [SelectMode(mode=initial_mode)]
            if initial_mode in ("example", "practice"):
                fast_path.append(ConfirmSkipWarning(accept=True))
            for cmd in fast_path:
                try:
                    result = await runner.dispatch(session_id, cmd)
                except ValueError as exc:
                    raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

        out = serialize_result(session_id, result)
        return CreateSessionResponse(**out.model_dump())

    @router.get("/sessions/{session_id}", response_model=SessionOut)
    async def get_session(session_id: UUID, request: Request) -> SessionOut:
        store: SessionStore = request.app.state.store
        snapshot: SessionSnapshot | None = await store.load(session_id)
        if snapshot is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Сессия не найдена")
        return serialize_session(session_id, snapshot.state, snapshot.ctx, effects=())

    @router.post("/sessions/{session_id}/commands", response_model=SessionOut)
    async def dispatch_command(
        session_id: UUID,
        body: CommandRequest,
        request: Request,
    ) -> SessionOut:
        store: SessionStore = request.app.state.store
        runner: SessionRunner = request.app.state.runner

        if await store.load(session_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Сессия не найдена")

        domain_cmd = to_domain_command(body.command)
        try:
            result = await runner.dispatch(session_id, domain_cmd)
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

        return serialize_result(session_id, result)

    @router.get("/audio/{key}")
    async def get_audio(key: str, request: Request) -> FileResponse:
        cache: FileAudioCache | None = getattr(request.app.state, "audio_cache", None)
        if cache is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Audio cache disabled")
        path = cache.path_for(key)
        if path is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Аудио не найдено")
        ext = path.suffix.lstrip(".").lower()
        media = {"wav": "audio/wav", "ogg": "audio/ogg", "mp3": "audio/mpeg"}.get(
            ext, "application/octet-stream"
        )
        return FileResponse(path, media_type=media)

    @router.post("/stt")
    async def stt_recognize(request: Request) -> dict[str, str]:
        stt: STTClient | None = getattr(request.app.state, "stt", None)
        if stt is None or not stt.available:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="STT недоступен (нет ключей или отключён)",
            )

        ctype = request.headers.get("content-type", "")
        if "multipart/form-data" not in ctype.lower():
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Ожидался multipart/form-data",
            )

        try:
            form = await request.form()
        except Exception as exc:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Не удалось распарсить multipart: {exc}",
            ) from exc

        audio_file = form.get("audio")
        if not isinstance(audio_file, UploadFile):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Ожидался multipart-файл в поле 'audio'",
            )

        data = await audio_file.read()
        if not data:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Пустое аудио")
        mime = audio_file.content_type or "audio/ogg;codecs=opus"
        text = await stt.recognize(data, mime)
        if text is None:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail="Не удалось распознать речь")
        return {"text": text}

    return router
