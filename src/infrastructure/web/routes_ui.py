"""UI-роуты: welcome и страница сессии."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from application.ports.session_store import SessionStore
from infrastructure.content.case_loader import resolve_case_id
from infrastructure.content.registry import DEFAULT_CASE_ID, all_cases, preza_file_for


def build_ui_router() -> APIRouter:
    router = APIRouter(tags=["ui"])

    @router.get("/", response_class=HTMLResponse)
    async def welcome(request: Request) -> HTMLResponse:
        templates: Jinja2Templates = request.app.state.templates
        products = [
            {"id": c.case_id, "label": c.label, "available": c.available} for c in all_cases()
        ]
        return templates.TemplateResponse(request, "welcome.html", {"products": products})

    @router.get("/session/{session_id}", response_class=HTMLResponse)
    async def session_page(session_id: UUID, request: Request) -> HTMLResponse:
        templates: Jinja2Templates = request.app.state.templates
        store: SessionStore = request.app.state.store

        case_id = DEFAULT_CASE_ID
        snapshot = await store.load(session_id)
        if snapshot is not None:
            # ДОПУЩЕНИЕ: SessionContext.product_id. Поправь имя поля при несовпадении.
            case_id = resolve_case_id(getattr(snapshot.ctx, "product_id", None))

        return templates.TemplateResponse(
            request,
            "session.html",
            {
                "session_id": str(session_id),
                "preza": preza_file_for(case_id),
            },
        )

    return router
