from __future__ import annotations

from typing import Literal

import pytest

from domain.context import SessionContext
from domain.states import FSMState
from domain.types import ChatMessage
from infrastructure.llm.stub_stage_director import StubStageDirector


def _ctx(*msgs: tuple[Literal["user", "assistant"], str]) -> SessionContext:
    return SessionContext(dialog_history=tuple(ChatMessage(role=r, text=t) for r, t in msgs))


@pytest.mark.asyncio
async def test_training_understood_keyword():
    sd = StubStageDirector()
    ctx = _ctx(("assistant", "..."), ("user", "понятно, давай дальше"))
    d = await sd.decide(state=FSMState.TRAINING, ctx=ctx)
    assert d.done is True
    assert d.outcome == "training_understood"


@pytest.mark.asyncio
async def test_training_continue():
    sd = StubStageDirector()
    ctx = _ctx(("user", "а что с лимитами?"))
    d = await sd.decide(state=FSMState.TRAINING, ctx=ctx)
    assert d.done is False
    assert d.outcome == "continue"


@pytest.mark.asyncio
async def test_example_accepted():
    sd = StubStageDirector()
    ctx = _ctx(("assistant", "..."), ("user", "хорошо, оформляйте карту"))
    d = await sd.decide(state=FSMState.EXAMPLE, ctx=ctx)
    assert d.outcome == "example_accepted"
    assert d.done is True


@pytest.mark.asyncio
async def test_example_refused_3x():
    sd = StubStageDirector()
    ctx = _ctx(
        ("user", "не нужно"),
        ("assistant", "..."),
        ("user", "не хочу"),
        ("assistant", "..."),
        ("user", "отказываюсь"),
    )
    d = await sd.decide(state=FSMState.EXAMPLE, ctx=ctx)
    assert d.outcome == "example_refused_3x"
    assert d.done is True


@pytest.mark.asyncio
async def test_practice_accepted():
    sd = StubStageDirector()
    ctx = _ctx(("user", "..."), ("user", "согласен, оформляю"))
    d = await sd.decide(state=FSMState.PRACTICE, ctx=ctx)
    assert d.outcome == "practice_accepted"


@pytest.mark.asyncio
async def test_knowledge_understood():
    sd = StubStageDirector()
    ctx = _ctx(("user", "всё ясно"))
    d = await sd.decide(state=FSMState.KNOWLEDGE, ctx=ctx)
    assert d.outcome == "knowledge_understood"


@pytest.mark.asyncio
async def test_non_stage_state():
    sd = StubStageDirector()
    d = await sd.decide(state=FSMState.MENU, ctx=_ctx())
    assert d.done is False
