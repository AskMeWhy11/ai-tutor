"""Тесты GigaChatAvatar (с моком SDK)."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import pytest

from domain.context import SessionContext
from domain.states import FSMState
from infrastructure.llm.prompt_store import PromptStore
from infrastructure.llm.stub_avatar import StubAvatar


@pytest.fixture(autouse=True)
def _stub_gigachat_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    """Подменяем gigachat.models на лёгкие заглушки, чтобы тесты не требовали SDK."""

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

    pkg = types.ModuleType("gigachat")
    sys.modules["gigachat"] = pkg
    sys.modules["gigachat.models"] = models


def _make_response(content: str) -> Any:
    class _Msg:
        def __init__(self, c: str) -> None:
            self.content = c

    class _Choice:
        def __init__(self, c: str) -> None:
            self.message = _Msg(c)

    class _Resp:
        def __init__(self, c: str) -> None:
            self.choices = [_Choice(c)]

    return _Resp(content)


class _ClientOk:
    def __init__(self, reply: str) -> None:
        self._reply = reply
        self.calls: list[Any] = []

    async def achat(self, payload: Any) -> Any:
        self.calls.append(payload)
        return _make_response(self._reply)


class _ClientBoom:
    async def achat(self, payload: Any) -> Any:
        raise RuntimeError("network down")


@pytest.fixture()
def prompt_store(tmp_path: Path) -> PromptStore:
    store = PromptStore(tmp_path / "templates.json")
    snap = store.snapshot()
    store.replace_all(system_prompt="Ты — наставник банка.", templates=snap.templates)
    return store


@pytest.mark.asyncio
async def test_returns_llm_text_when_call_succeeds(prompt_store: PromptStore) -> None:
    from infrastructure.llm.gigachat_avatar import GigaChatAvatar

    stub = StubAvatar(prompt_store)
    client = _ClientOk("Перефразированный текст.")
    avatar = GigaChatAvatar(
        client=client,  # type: ignore[arg-type]
        prompt_store=prompt_store,
        fallback=stub,
    )
    text = await avatar.next_message(FSMState.WELCOME, SessionContext())
    assert text == "Перефразированный текст."
    assert client.calls, "ожидался вызов GigaChat"


@pytest.mark.asyncio
async def test_falls_back_on_llm_failure(prompt_store: PromptStore) -> None:
    from infrastructure.llm.gigachat_avatar import GigaChatAvatar

    stub = StubAvatar(prompt_store)
    base = await stub.next_message(FSMState.WELCOME, SessionContext())
    avatar = GigaChatAvatar(
        client=_ClientBoom(),  # type: ignore[arg-type]
        prompt_store=prompt_store,
        fallback=stub,
    )
    text = await avatar.next_message(FSMState.WELCOME, SessionContext())
    assert text == base


@pytest.mark.asyncio
async def test_skips_llm_when_system_prompt_empty(tmp_path: Path) -> None:
    from infrastructure.llm.gigachat_avatar import GigaChatAvatar

    store = PromptStore(tmp_path / "t.json")
    snap = store.snapshot()
    store.replace_all(system_prompt="", templates=snap.templates)
    stub = StubAvatar(store)
    base = await stub.next_message(FSMState.WELCOME, SessionContext())
    client = _ClientOk("LLM-text")
    avatar = GigaChatAvatar(client=client, prompt_store=store, fallback=stub)  # type: ignore[arg-type]
    text = await avatar.next_message(FSMState.WELCOME, SessionContext())
    assert text == base
    assert not client.calls


@pytest.mark.asyncio
async def test_hint_delegated_to_fallback(prompt_store: PromptStore) -> None:
    from infrastructure.llm.gigachat_avatar import GigaChatAvatar

    stub = StubAvatar(prompt_store)
    avatar = GigaChatAvatar(
        client=_ClientOk("X"),  # type: ignore[arg-type]
        prompt_store=prompt_store,
        fallback=stub,
    )
    expected = await stub.next_hint(FSMState.EXAMPLE, SessionContext())
    actual = await avatar.next_hint(FSMState.EXAMPLE, SessionContext())
    assert actual == expected
