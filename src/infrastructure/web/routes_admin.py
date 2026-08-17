"""Админ-роуты для редактирования промпт-шаблонов и промптов режимов."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from domain.states import FSMState, Mode
from domain.types import ZONE_ORDER
from infrastructure.content.case_loader import (
    case_dir,
    default_case_dir,
    invalidate_case_cache,
    read_checklist_raw,
    restore_default,
    write_checklist_raw,
)
from infrastructure.content.registry import (
    CASE_REGISTRY,
    DEFAULT_CASE_ID,
    available_case_ids,
)
from infrastructure.llm.prompt_store import (
    DYNAMIC_STATES,
    EDITABLE_STATES,
    PromptStore,
)
from infrastructure.web.security import (
    ADMIN_COOKIE_NAME,
    check_credentials,
    issue_token,
    require_admin,
)

logger = logging.getLogger(__name__)

_MODE_LABELS: dict[Mode, str] = {
    Mode.TRAINING: "TRAINING — наставник, рассказывает теорию",
    Mode.EXAMPLE: "EXAMPLE — играет роль сотрудника банка (сотрудник = клиент)",
    Mode.PRACTICE: "PRACTICE — играет роль клиента (сотрудник = продавец)",
    Mode.KNOWLEDGE: "KNOWLEDGE — наставник, прокачивает западающие зоны",
}

_ZONE_LABELS: dict[str, str] = {
    "needs": "Выявление потребности",
    "pitch": "Презентация продукта",
    "conditions": "Условия и возражения",
}

_ALLOWED_FILES: dict[str, str] = {
    "dialogues": "dialogues.md",
    "facts": "facts.md",
    "checklist": "checklist.json",
}
_MAX_UPLOAD_BYTES: int = 1 * 1024 * 1024  # 1 МБ


def _allowed_cases() -> frozenset[str]:
    return available_case_ids()


def _resolve_case_id(case_id: str | None) -> str:
    """Нормализовать выбранный кейс (query/form) к доступному."""
    if case_id and case_id in _allowed_cases():
        return case_id
    return DEFAULT_CASE_ID


def _case_options(selected: str) -> list[dict[str, Any]]:
    allowed = _allowed_cases()
    return [
        {"id": c.case_id, "label": c.label, "selected": c.case_id == selected}
        for c in CASE_REGISTRY
        if c.case_id in allowed
    ]


def _store(request: Request) -> PromptStore:
    store: PromptStore | None = getattr(request.app.state, "prompt_store", None)
    if store is None:
        raise HTTPException(status_code=500, detail="PromptStore is not configured")
    return store


def _build_items(snap: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for s in EDITABLE_STATES:
        items.append(
            {
                "key": s.value,
                "label": s.value,
                "text": snap.templates.get(s, ""),
                "dynamic": False,
            }
        )
    for s in DYNAMIC_STATES:
        items.append({"key": s.value, "label": s.value, "text": "", "dynamic": True})
    return items


def _build_modes(snap: Any) -> list[dict[str, Any]]:
    return [
        {
            "key": m.value,
            "label": _MODE_LABELS[m],
            "text": snap.mode_prompts.get(m, ""),
        }
        for m in Mode
    ]


def _build_checklist_view(case_id: str) -> list[dict[str, Any]]:
    raw = read_checklist_raw(case_id)
    return [
        {
            "key": zone,
            "label": _ZONE_LABELS.get(zone, zone),
            "entries": raw.get(zone, []),
        }
        for zone in ZONE_ORDER
    ]


def _has_default(case_id: str, filename: str) -> bool:
    return (default_case_dir(case_id) / filename).exists()


def _resolve_case_file(case_id: str, file_key: str) -> tuple[str, Any]:
    if case_id not in _allowed_cases():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown case")
    filename = _ALLOWED_FILES.get(file_key)
    if filename is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown file")
    return filename, case_dir(case_id) / filename


def _parse_lines(raw: str) -> list[str]:
    """Превратить многострочный textarea в список непустых строк."""
    return [line.strip() for line in raw.replace("\r", "").split("\n") if line.strip()]


def _parse_checklist_form(
    form_items: list[tuple[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Распарсить поля cl__{zone}__{idx}__{field} из формы.

    Поддерживает удаление: если есть `delete__{zone}__{idx}=on`, элемент пропускается.
    Возвращает словарь зон → отсортированный по idx список элементов.
    """
    buckets: dict[str, dict[int, dict[str, Any]]] = {z: {} for z in ZONE_ORDER}
    deletes: set[tuple[str, int]] = set()

    for name, value in form_items:
        if name.startswith("delete__"):
            try:
                _, zone, idx_s = name.split("__", 2)
            except ValueError:
                continue
            if zone not in buckets:
                continue
            try:
                deletes.add((zone, int(idx_s)))
            except ValueError:
                continue
            continue

        if not name.startswith("cl__"):
            continue
        try:
            _, zone, idx_s, field = name.split("__", 3)
        except ValueError:
            continue
        if zone not in buckets:
            continue
        try:
            idx = int(idx_s)
        except ValueError:
            continue

        item = buckets[zone].setdefault(idx, {})
        sval = str(value)
        if field in {"example_phrases", "keywords"}:
            item[field] = _parse_lines(sval)
        elif field in {"id", "name", "criteria"}:
            item[field] = sval.strip()

    out: dict[str, list[dict[str, Any]]] = {}
    for zone, by_idx in buckets.items():
        ordered: list[dict[str, Any]] = []
        for idx in sorted(by_idx.keys()):
            if (zone, idx) in deletes:
                continue
            it = by_idx[idx]
            it.setdefault("id", "")
            it.setdefault("name", "")
            it.setdefault("criteria", "")
            it.setdefault("example_phrases", [])
            it.setdefault("keywords", [])
            ordered.append(it)
        out[zone] = ordered
    return out


def build_admin_router() -> list[APIRouter]:
    # ---------- Публичные роуты аутентификации (без require_admin) ----------
    public = APIRouter(prefix="/admin", tags=["admin"])

    @public.get("/login", response_class=HTMLResponse)
    def login_form(
        request: Request,
        next: str = "/admin/prompts",
        error: int = 0,
    ) -> Any:
        settings = request.app.state.settings
        if not settings.admin_password:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Admin panel is disabled (ADMIN_PASSWORD is not set)",
            )
        templates = request.app.state.templates
        return templates.TemplateResponse(
            request,
            "admin_login.html",
            {"next": next, "error": bool(error)},
        )

    @public.post("/login")
    async def login_submit(request: Request) -> RedirectResponse:
        from urllib.parse import quote

        settings = request.app.state.settings
        form = await request.form()
        username = str(form.get("username", ""))
        password = str(form.get("password", ""))
        next_url = str(form.get("next", "/admin/prompts")) or "/admin/prompts"
        if not next_url.startswith("/admin"):
            next_url = "/admin/prompts"

        if not check_credentials(settings, username, password):
            return RedirectResponse(
                url=f"/admin/login?next={quote(next_url, safe='')}&error=1",
                status_code=status.HTTP_303_SEE_OTHER,
            )

        token = issue_token(settings, username)
        resp = RedirectResponse(url=next_url, status_code=status.HTTP_303_SEE_OTHER)
        resp.set_cookie(
            key=ADMIN_COOKIE_NAME,
            value=token,
            max_age=int(settings.admin_session_ttl_seconds),
            httponly=True,
            secure=bool(settings.admin_cookie_secure),
            samesite="lax",
            path="/admin",
        )
        return resp

    @public.post("/logout")
    def logout() -> RedirectResponse:
        resp = RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)
        resp.delete_cookie(ADMIN_COOKIE_NAME, path="/admin")
        return resp

    # ---------- Защищённые роуты ----------
    router = APIRouter(
        prefix="/admin",
        tags=["admin"],
        dependencies=[Depends(require_admin)],
    )

    @router.get("/prompts", response_class=HTMLResponse)
    def get_prompts(
        request: Request,
        case_id: str = "",
        saved: int = 0,
        case_saved: str = "",
    ) -> Any:
        store = _store(request)
        cid = _resolve_case_id(case_id)
        snap = store.snapshot(cid)
        templates = request.app.state.templates

        defaults_available = {
            key: _has_default(cid, filename) for key, filename in _ALLOWED_FILES.items()
        }
        cases = _case_options(cid)
        case_label = next((c["label"] for c in cases if c["id"] == cid), cid)

        return templates.TemplateResponse(
            request,
            "admin_prompts.html",
            {
                "case_id": cid,
                "case_label": case_label,
                "cases": cases,
                "system_prompt": snap.system_prompt,
                "items": _build_items(snap),
                "modes": _build_modes(snap),
                "quiz_prompt": snap.quiz_prompt,
                "stage_director_prompt": snap.stage_director_prompt,
                "customer_profile_system_prompt": snap.customer_profile_system_prompt,
                "customer_profile_user_prompt": snap.customer_profile_user_prompt,
                "saved": bool(saved),
                "case_saved": case_saved,
                "checklist_zones": _build_checklist_view(cid),
                "defaults_available": defaults_available,
            },
        )

    @router.post("/prompts")
    async def update_prompts(request: Request) -> Any:
        store = _store(request)
        form = await request.form()

        cid = _resolve_case_id(str(form.get("case_id", "")))
        system_prompt = str(form.get("system_prompt", ""))
        quiz_prompt = str(form.get("quiz_prompt", ""))
        stage_director_prompt = str(form.get("stage_director_prompt", ""))
        profile_system = str(form.get("customer_profile_system_prompt", ""))
        profile_user = str(form.get("customer_profile_user_prompt", ""))

        editable_names = {s.value: s for s in EDITABLE_STATES}
        templates: dict[FSMState, str] = {}
        mode_names = {m.value: m for m in Mode}
        mode_prompts: dict[Mode, str] = {}

        for raw_name, raw_value in form.multi_items():
            if raw_name.startswith("tpl__"):
                state = editable_names.get(raw_name[len("tpl__") :])
                if state is None:
                    continue
                templates[state] = str(raw_value)
            elif raw_name.startswith("mode__"):
                mode = mode_names.get(raw_name[len("mode__") :])
                if mode is None:
                    continue
                mode_prompts[mode] = str(raw_value)

        store.replace_all(
            system_prompt=system_prompt,
            templates=templates,
            mode_prompts=mode_prompts,
            quiz_prompt=quiz_prompt,
            stage_director_prompt=stage_director_prompt,
            customer_profile_system_prompt=profile_system or None,
            customer_profile_user_prompt=profile_user or None,
            case_id=cid,
        )
        return RedirectResponse(
            url=f"/admin/prompts?case_id={cid}&saved=1",
            status_code=303,
        )

    # ---------- Файлы кейса: download / upload / restore ----------

    @router.get("/case/{case_id}/{file_key}")
    def download_case_file(case_id: str, file_key: str) -> FileResponse:
        filename, path = _resolve_case_file(case_id, file_key)
        if not path.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
        media = (
            "application/json; charset=utf-8"
            if filename.endswith(".json")
            else "text/markdown; charset=utf-8"
        )
        return FileResponse(path=path, media_type=media, filename=filename)

    @router.post("/case/{case_id}/{file_key}")
    async def upload_case_file(
        case_id: str,
        file_key: str,
        file: UploadFile,
    ) -> RedirectResponse:
        filename, path = _resolve_case_file(case_id, file_key)
        data = await file.read()
        if len(data) > _MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"File too large (>{_MAX_UPLOAD_BYTES} bytes)",
            )
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File must be UTF-8 encoded",
            ) from exc
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        invalidate_case_cache(case_id)
        logger.info("Case file updated: %s/%s (%d bytes)", case_id, filename, len(data))
        return RedirectResponse(
            url=f"/admin/prompts?case_id={case_id}&case_saved={file_key}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @router.post("/case/{case_id}/{file_key}/restore")
    def restore_case_file(case_id: str, file_key: str) -> RedirectResponse:
        filename, _ = _resolve_case_file(case_id, file_key)
        ok = restore_default(case_id, filename)
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Default file not found",
            )
        return RedirectResponse(
            url=f"/admin/prompts?case_id={case_id}&case_saved={file_key}-restored",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # ---------- Чек-лист: сохранение / добавление / удаление ----------

    @router.post("/case/{case_id}/checklist/edit")
    async def save_checklist(case_id: str, request: Request) -> RedirectResponse:
        if case_id not in _allowed_cases():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown case")
        form = await request.form()
        items = list(form.multi_items())

        add_zone: str | None = None
        for name, value in items:
            if name == "action" and str(value).startswith("add_"):
                candidate = str(value)[len("add_") :]
                if candidate in ZONE_ORDER:
                    add_zone = candidate
                    break

        parsed = _parse_checklist_form(items)
        if add_zone is not None:
            parsed.setdefault(add_zone, []).append(
                {
                    "id": "",
                    "name": "",
                    "criteria": "",
                    "example_phrases": [],
                    "keywords": [],
                }
            )

        write_checklist_raw(case_id, parsed)
        suffix = "checklist-added" if add_zone else "checklist"
        return RedirectResponse(
            url=f"/admin/prompts?case_id={case_id}&case_saved={suffix}#checklist",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # ---------- Промпты режимов / квиз: restore ----------

    @router.post("/prompts/{case_id}/mode/{mode_key}/restore")
    def restore_mode_prompt(case_id: str, mode_key: str, request: Request) -> RedirectResponse:
        cid = _resolve_case_id(case_id)
        try:
            mode = Mode(mode_key)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Unknown mode"
            ) from exc
        _store(request).restore_mode_prompt(mode, cid)
        logger.info("Mode prompt restored: %s/%s", cid, mode_key)
        return RedirectResponse(
            url=f"/admin/prompts?case_id={cid}&case_saved=mode-{mode_key}-restored",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @router.post("/prompts/{case_id}/quiz/restore")
    def restore_quiz_prompt(case_id: str, request: Request) -> RedirectResponse:
        cid = _resolve_case_id(case_id)
        _store(request).restore_quiz_prompt(cid)
        logger.info("Quiz prompt restored: %s", cid)
        return RedirectResponse(
            url=f"/admin/prompts?case_id={cid}&case_saved=quiz-restored",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @router.post("/prompts/{case_id}/customer-profile/restore")
    def restore_customer_profile(case_id: str, request: Request) -> RedirectResponse:
        cid = _resolve_case_id(case_id)
        _store(request).restore_customer_profile_prompts(cid)
        logger.info("Customer profile prompts restored: %s", cid)
        return RedirectResponse(
            url=f"/admin/prompts?case_id={cid}&case_saved=customer-profile-restored",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return [public, router]
