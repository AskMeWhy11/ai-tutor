"""SessionRunner: авто-оценка PRACTICE через PracticeEvaluator."""

from __future__ import annotations

from uuid import uuid4

import pytest

from application.commands import DialogDone
from application.fsm_service import FSMService
from application.session_runner import SessionRunner
from domain.context import SessionContext
from domain.states import FSMState, Mode
from domain.types import ChatMessage, Zone
from tests.fakes.in_memory_session_store import InMemorySessionStore


class _FakeEvaluator:
    def __init__(self, weak: tuple[Zone, ...]) -> None:
        self.weak = weak
        self.calls: list[tuple[ChatMessage, ...]] = []

    async def evaluate(
        self,
        history: tuple[ChatMessage, ...],
        *,
        case_id: str | None = None,
    ) -> tuple[Zone, ...]:
        self.calls.append(history)
        return self.weak


class _BoomEvaluator:
    async def evaluate(
        self,
        history: tuple[ChatMessage, ...],
        *,
        case_id: str | None = None,
    ) -> tuple[Zone, ...]:
        raise RuntimeError("LLM down")


@pytest.mark.asyncio
async def test_dialog_done_triggers_practice_success_when_no_weak_zones() -> None:
    store = InMemorySessionStore()
    sid = uuid4()
    history = (
        ChatMessage(role="assistant", text="..."),
        ChatMessage(role="user", text="Предлагаю ФИКС, до 50 тыс. снятий бесплатно"),
    )
    await store.save(
        sid,
        FSMState.PRACTICE,
        SessionContext(
            completed_modes=frozenset({Mode.TRAINING, Mode.EXAMPLE}),
            dialog_history=history,
        ),
    )
    evaluator = _FakeEvaluator(weak=())
    runner = SessionRunner(
        fsm=FSMService(),
        store=store,
        avatar=None,
        practice_evaluator=evaluator,
    )

    result = await runner.dispatch(sid, DialogDone())

    assert evaluator.calls == [history]
    assert result.new_state is FSMState.FINISH
    assert Mode.PRACTICE in result.new_ctx.completed_modes
    assert result.new_ctx.weak_zones_remaining == ()


@pytest.mark.asyncio
async def test_dialog_done_triggers_partial_when_weak_zones_present() -> None:
    store = InMemorySessionStore()
    sid = uuid4()
    await store.save(
        sid,
        FSMState.PRACTICE,
        SessionContext(
            completed_modes=frozenset({Mode.TRAINING, Mode.EXAMPLE}),
            dialog_history=(ChatMessage(role="user", text="что-то"),),
        ),
    )
    evaluator = _FakeEvaluator(weak=("needs", "pitch"))
    runner = SessionRunner(
        fsm=FSMService(),
        store=store,
        avatar=None,
        practice_evaluator=evaluator,
    )

    result = await runner.dispatch(sid, DialogDone())

    assert result.new_state is FSMState.KNOWLEDGE
    assert result.new_ctx.weak_zones_remaining == ("needs", "pitch")
    assert Mode.PRACTICE not in result.new_ctx.completed_modes


@pytest.mark.asyncio
async def test_evaluator_failure_keeps_state_in_practice_eval() -> None:
    """Если LLM-оценщик бросил — остаёмся в PRACTICE_EVAL без авто-команды.

    UI/оператор сможет повторить попытку или эмитировать PracticeEvaluated вручную.
    """
    store = InMemorySessionStore()
    sid = uuid4()
    await store.save(
        sid,
        FSMState.PRACTICE,
        SessionContext(dialog_history=(ChatMessage(role="user", text="x"),)),
    )
    runner = SessionRunner(
        fsm=FSMService(),
        store=store,
        avatar=None,
        practice_evaluator=_BoomEvaluator(),
    )
    result = await runner.dispatch(sid, DialogDone())
    assert result.new_state is FSMState.PRACTICE_EVAL


@pytest.mark.asyncio
async def test_no_evaluator_means_no_auto_command() -> None:
    store = InMemorySessionStore()
    sid = uuid4()
    await store.save(
        sid,
        FSMState.PRACTICE,
        SessionContext(dialog_history=(ChatMessage(role="user", text="x"),)),
    )
    runner = SessionRunner(fsm=FSMService(), store=store, avatar=None)
    result = await runner.dispatch(sid, DialogDone())
    assert result.new_state is FSMState.PRACTICE_EVAL
