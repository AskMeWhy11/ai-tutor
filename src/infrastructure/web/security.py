"""HTTP Basic-аутентификация для админ-роутов."""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

_basic = HTTPBasic(realm="ai-tutor admin")

BasicCreds = Annotated[HTTPBasicCredentials, Depends(_basic)]


def require_admin(request: Request, credentials: BasicCreds) -> str:
    """Проверка логина/пароля админа.

    - Если ADMIN_PASSWORD пуст в settings — возвращаем 503 (админка отключена).
    - Сравнение через ``secrets.compare_digest`` (защита от тайминг-атак).
    - При неуспехе — 401 с ``WWW-Authenticate: Basic``.
    """
    settings = request.app.state.settings
    expected_user = (settings.admin_username or "").encode("utf-8")
    expected_pass = (settings.admin_password or "").encode("utf-8")

    if not expected_pass:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin panel is disabled (ADMIN_PASSWORD is not set)",
        )

    given_user = credentials.username.encode("utf-8")
    given_pass = credentials.password.encode("utf-8")

    user_ok = secrets.compare_digest(given_user, expected_user)
    pass_ok = secrets.compare_digest(given_pass, expected_pass)

    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": 'Basic realm="ai-tutor admin"'},
        )

    return credentials.username
