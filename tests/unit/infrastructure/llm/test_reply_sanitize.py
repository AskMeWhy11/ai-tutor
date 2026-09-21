"""Очистка и валидация реплики LLM перед показом сотруднику.

Жалобы пользователей: в баббл попадали служебные обрывки — "Завершаем?QT",
отдельные сообщения "rightarrow" и "IP". Чаще всего на стыках режимов,
то есть в статичных состояниях, где санитайзинга не было вовсе.
"""

from __future__ import annotations

import logging
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from domain.context import SessionContext
from domain.states import FSMState
from infrastructure.llm.content_render import is_usable_reply, sanitize_reply
from infrastructure.llm.prompt_store import PromptStore
from infrastructure.llm.stub_avatar import StubAvatar

pytestmark = pytest.mark.unit


# ---------- sanitize_reply ----------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Хвостовой обрывок токенизации — ровно случай со скриншота.
        ("Завершаем?QT", "Завершаем?"),
        ("Теперь перейдём к проверке знаний.IP", "Теперь перейдём к проверке знаний."),
        ("Всё понятно?rightarrow", "Всё понятно?"),
        # Теги эмоций убираются как и раньше.
        ("[happy] Отличная работа!", "Отличная работа!"),
        ("[annoyed]Не понимаю вас.", "Не понимаю вас."),
        # Латиница через пробел — законный текст, не трогаем.
        ("Разберём технику SPIN", "Разберём технику SPIN"),
        ("Это называется CRM", "Это называется CRM"),
        # Обычная реплика не меняется.
        ("Здравствуйте! Чем помочь?", "Здравствуйте! Чем помочь?"),
    ],
)
def test_sanitize_reply(raw: str, expected: str) -> None:
    assert sanitize_reply(raw) == expected


# ---------- is_usable_reply ----------


@pytest.mark.parametrize(
    "text",
    ["Хорошо.", "Да, верно.", "Продолжим?", "Ок, переходим к практике."],
)
def test_usable_keeps_short_russian(text: str) -> None:
    assert is_usable_reply(text) is True


@pytest.mark.parametrize("text", ["", "   ", "rightarrow", "IP", "QT", "???", "[happy]"])
def test_usable_rejects_garbage(text: str) -> None:
    assert is_usable_reply(text) is False


# ---------- интеграция с аватаром ----------


@pytest.fixture(autouse=True)
def _stub_gigachat_sdk() -> None:
    models = types.ModuleType("gigachat.models")

    class Messages:
        def __init__(self, role: str, content: str) -> None:
            self.role = role
            self.content = content

    class MessagesRole:
        SYSTEM = "system"
        USER = "user"

    class Chat:
        def __init__(self, messages: list[Messages]) -> None:
            self.messages = messages
            self.model: str | None = None

    models.Messages = Messages  # type: ignore[attr-defined]
    models.MessagesRole = MessagesRole  # type: ignore[attr-defined]
    models.Chat = Chat  # type: ignore[attr-defined]
    sys.modules["gigachat"] = types.ModuleType("gigachat")
    sys.modules["gigachat.models"] = models


class _Client:
    def __init__(self, reply: str) -> None:
        self._reply = reply

    async def achat(self, payload: Any) -> Any:
        message = types.SimpleNamespace(content=self._reply)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])


@pytest.fixture()
def store(tmp_path: Path) -> PromptStore:
    s = PromptStore(tmp_path / "templates.json")
    snap = s.snapshot()
    s.replace_all(system_prompt="Ты — наставник банка.", templates=snap.templates)
    return s


@pytest.mark.asyncio
async def test_static_state_strips_trailing_artifact(store: PromptStore) -> None:
    """WELCOME — статичное состояние: раньше мусор уходил в баббл дословно."""
    from infrastructure.llm.gigachat_avatar import GigaChatAvatar

    avatar = GigaChatAvatar(
        client=_Client("Начнём тренировку?QT"),  # type: ignore[arg-type]
        prompt_store=store,
        fallback=StubAvatar(store),
    )
    assert await avatar.next_message(FSMState.WELCOME, SessionContext()) == "Начнём тренировку?"


@pytest.mark.asyncio
async def test_static_state_rejects_latin_garbage(
    store: PromptStore,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from infrastructure.llm.gigachat_avatar import GigaChatAvatar

    stub = StubAvatar(store)
    base = await stub.next_message(FSMState.WELCOME, SessionContext())
    avatar = GigaChatAvatar(
        client=_Client("rightarrow"),  # type: ignore[arg-type]
        prompt_store=store,
        fallback=stub,
    )
    with caplog.at_level(logging.WARNING):
        text = await avatar.next_message(FSMState.WELCOME, SessionContext())

    assert text == base
    assert "static reply rejected" in caplog.text
    assert "rightarrow" in caplog.text


@pytest.mark.asyncio
async def test_mode_state_rejects_latin_garbage(
    store: PromptStore,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from infrastructure.llm.gigachat_avatar import GigaChatAvatar

    stub = StubAvatar(store)
    ctx = SessionContext(product_id="cc_novichok")
    avatar = GigaChatAvatar(
        client=_Client("IP"),  # type: ignore[arg-type]
        prompt_store=store,
        fallback=stub,
    )
    with caplog.at_level(logging.WARNING):
        text = await avatar.next_message(FSMState.PRACTICE, ctx)

    assert text == await stub.next_message(FSMState.PRACTICE, ctx)
    assert "reply rejected" in caplog.text
