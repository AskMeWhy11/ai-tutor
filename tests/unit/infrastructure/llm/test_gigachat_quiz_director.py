"""GigaChatQuizDirector: история квиза передаётся как реальные реплики,
и роль assistant не роняет вызов в фолбэк."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from domain.context import SessionContext
from domain.types import ChatMessage
from infrastructure.llm.gigachat_quiz_director import GigaChatQuizDirector


class _FakeResp:
    def __init__(self, content: str) -> None:
        self.choices = [type("C", (), {"message": type("M", (), {"content": content})()})()]


class _FakeClient:
    def __init__(self, content: str) -> None:
        self._content = content
        self.sent_roles: list[Any] = []

    async def achat(self, payload: Any) -> _FakeResp:
        self.sent_roles = [m.role for m in payload.messages]
        return _FakeResp(self._content)


@pytest.mark.asyncio
async def test_quiz_history_passed_and_assistant_role_does_not_fallback() -> None:
    client = _FakeClient(
        '{"verdict":"correct","explanation":"","next_question":"Q2","done":false}'
    )
    store = MagicMock()
    store.get_quiz_prompt.return_value = "SYSTEM {FACTS}"
    fallback = MagicMock()

    director = GigaChatQuizDirector(client=client, prompt_store=store, fallback=fallback)  # type: ignore[arg-type]
    ctx = SessionContext(
        product_id="xpv",
        quiz_history=(ChatMessage(role="assistant", text="Q1"),),
    )

    turn = await director.next_turn(ctx, "мой ответ")

    assert turn.verdict == "correct"
    assert turn.next_question == "Q2"
    # История квиза действительно ушла в модель отдельной репликой.
    roles = [str(r).lower() for r in client.sent_roles]
    assert any("assistant" in r for r in roles)
    # И это НЕ уронило вызов в фолбэк.
    fallback.next_turn.assert_not_called()
