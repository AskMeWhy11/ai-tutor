"""StageDirector: теорию техники продаж нельзя закрыть раньше минимума реплик."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from domain.context import SessionContext
from domain.states import FSMState
from domain.types import ChatMessage
from infrastructure.llm.gigachat_stage_director import (
    _MIN_TRAINING_AVATAR_TURNS,
    GigaChatStageDirector,
)

_DONE_JSON = '{"done": true, "outcome": "training_understood", "reason": "ok"}'


class _FakeResp:
    def __init__(self, content: str) -> None:
        self.choices = [type("C", (), {"message": type("M", (), {"content": content})()})()]


class _FakeClient:
    def __init__(self) -> None:
        self.calls = 0

    async def achat(self, payload: Any) -> _FakeResp:
        self.calls += 1
        return _FakeResp(_DONE_JSON)


def _history(avatar_turns: int) -> tuple[ChatMessage, ...]:
    out: list[ChatMessage] = []
    for i in range(avatar_turns):
        out.append(ChatMessage(role="assistant", text=f"теория {i}"))
        out.append(ChatMessage(role="user", text="да"))
    return tuple(out)


def _director(client: _FakeClient) -> GigaChatStageDirector:
    store = MagicMock()
    store.get_stage_director_prompt.return_value = "SD"
    return GigaChatStageDirector(client=client, prompt_store=store, fallback=MagicMock())  # type: ignore[arg-type]


@pytest.mark.asyncio
@pytest.mark.parametrize("turns", range(1, _MIN_TRAINING_AVATAR_TURNS))
async def test_training_not_closed_before_floor_for_techniques(turns: int) -> None:
    client = _FakeClient()
    director = _director(client)

    decision = await director.decide(
        state=FSMState.TRAINING,
        ctx=SessionContext(product_id="xpv", dialog_history=_history(turns)),
    )

    # Даже если LLM хочет закрыть — держим стадию и вообще не зовём LLM.
    assert decision.done is False
    assert decision.outcome == "continue"
    assert client.calls == 0


@pytest.mark.asyncio
async def test_training_closes_once_floor_reached() -> None:
    client = _FakeClient()
    director = _director(client)

    decision = await director.decide(
        state=FSMState.TRAINING,
        ctx=SessionContext(product_id="xpv", dialog_history=_history(_MIN_TRAINING_AVATAR_TURNS)),
    )

    assert decision.done is True
    assert decision.outcome == "training_understood"
    assert client.calls == 1


@pytest.mark.asyncio
async def test_floor_does_not_apply_to_cc_novichok() -> None:
    client = _FakeClient()
    director = _director(client)

    decision = await director.decide(
        state=FSMState.TRAINING,
        ctx=SessionContext(product_id="cc_novichok", dialog_history=_history(1)),
    )

    assert decision.done is True
    assert client.calls == 1
