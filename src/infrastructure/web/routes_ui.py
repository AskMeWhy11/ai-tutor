"""UI-роуты: welcome и страница сессии."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates


def build_ui_router() -> APIRouter:
    router = APIRouter(tags=["ui"])

    @router.get("/", response_class=HTMLResponse)
    async def welcome(request: Request) -> HTMLResponse:
        templates: Jinja2Templates = request.app.state.templates
        return templates.TemplateResponse(request, "welcome.html", {})

    @router.get("/session/{session_id}", response_class=HTMLResponse)
    async def session_page(session_id: UUID, request: Request) -> HTMLResponse:
        templates: Jinja2Templates = request.app.state.templates
        return templates.TemplateResponse(
            request,
            "session.html",
            {"session_id": str(session_id)},
        )

    return router
