"""Аутентификация админ-роутов через форму логина и подписанную cookie."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from typing import TYPE_CHECKING

from fastapi import HTTPException, Request, status
from fastapi.responses import RedirectResponse

if TYPE_CHECKING:
    from infrastructure.config import Settings

ADMIN_COOKIE_NAME = "admin_session"
_LOGIN_PATH = "/admin/login"


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def _sign(payload: bytes, key: bytes) -> str:
    return _b64e(hmac.new(key, payload, hashlib.sha256).digest())


def issue_token(settings: Settings, username: str) -> str:
    """Сформировать подписанный токен вида ``user.exp.signature``."""
    exp = int(time.time()) + int(settings.admin_session_ttl_seconds)
    payload = f"{username}.{exp}".encode()
    sig = _sign(payload, settings.admin_signing_key)
    return f"{_b64e(payload)}.{sig}"


def verify_token(settings: Settings, token: str | None) -> str | None:
    """Проверить токен. Возвращает username или None."""
    if not token:
        return None
    try:
        payload_b64, sig = token.rsplit(".", 1)
        payload = _b64d(payload_b64)
    except (ValueError, Exception):
        return None

    expected = _sign(payload, settings.admin_signing_key)
    if not hmac.compare_digest(sig, expected):
        return None

    try:
        username, exp_s = payload.decode("utf-8").rsplit(".", 1)
        exp = int(exp_s)
    except ValueError:
        return None

    if exp < int(time.time()):
        return None
    return username


def check_credentials(settings: Settings, username: str, password: str) -> bool:
    """Сверка логина/пароля (защита от тайминг-атак)."""
    if not settings.admin_password:
        return False
    user_ok = secrets.compare_digest(
        username.encode("utf-8"), (settings.admin_username or "").encode("utf-8")
    )
    pass_ok = secrets.compare_digest(
        password.encode("utf-8"), settings.admin_password.encode("utf-8")
    )
    return user_ok and pass_ok


def require_admin(request: Request) -> str:
    """Guard для админ-роутов: валидная cookie-сессия обязательна.

    - ADMIN_PASSWORD пуст → 503 (админка отключена).
    - Нет/протух токен → редирект на форму логина для GET-навигации,
      иначе 401 (для POST/API-подобных запросов).
    """
    settings = request.app.state.settings
    if not settings.admin_password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin panel is disabled (ADMIN_PASSWORD is not set)",
        )

    token = request.cookies.get(ADMIN_COOKIE_NAME)
    username = verify_token(settings, token)
    if username is not None:
        return username

    if request.method == "GET":
        next_url = request.url.path
        if request.url.query:
            next_url = f"{next_url}?{request.url.query}"
        raise _redirect_to_login(next_url)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Admin session required",
    )


class LoginRedirect(HTTPException):
    """HTTPException, несущий готовый RedirectResponse."""

    def __init__(self, response: RedirectResponse) -> None:
        super().__init__(status_code=response.status_code)
        self.response = response


def _redirect_to_login(next_url: str) -> LoginRedirect:
    from urllib.parse import quote

    url = f"{_LOGIN_PATH}?next={quote(next_url, safe='')}"
    return LoginRedirect(RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER))
