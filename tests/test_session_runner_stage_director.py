"""SessionRunner: интеграция со StageDirector."""

from __future__ import annotations

from uuid import uuid4

import pytest

from application.commands import UserMessage
from application.effects import EmitText, PersistSession
from application.fsm_service import FSMService
from application.ports.avatar import AvatarClient
from application.ports.practice_evaluator import PracticeEvaluator
from application.ports.stage_director import StageDecision, StageDirector
from application.session_runner import SessionRunner
from domain.context import SessionContext
from domain.states import FSMState
from domain.types import ChatMessage, Zone
from tests.fakes.in_memory_session_store import InMemorySessionStore


class _FixedAvatar(AvatarClient):
    def __init__(self, text: str = "ok") -> None:
        self.text = text
        self.calls: list[FSMState] = []

    async def next_message(self, state: FSMState, ctx: SessionContext) -> str:
        self.calls.append(state)
        return self.text

    async def next_hint(self, state: FSMState, ctx: SessionContext) -> str | None:
        return None


class _StageDirectorStub(StageDirector):
    def __init__(self, plan: list[StageDecision]) -> None:
        self._plan = plan
        self.calls: list[FSMState] = []

    async def decide(self, *, state: FSMState, ctx: SessionContext) -> StageDecision:
        self.calls.append(state)
        if not self._plan:
            return StageDecision(False, "continue", "")
        return self._plan.pop(0)


class _AllWeakEvaluator(PracticeEvaluator):
    async def evaluate(
        self,
        history: tuple[ChatMessage, ...],
        *,
        case_id: str | None = None,
    ) -> tuple[Zone, ...]:
        return ("needs", "pitch", "conditions")


@pytest.mark.asyncio
async def test_training_close_chain_jumps_to_training_quiz() -> None:
    """TRAINING + training_understood → TheoryDone → TRAINING_QUIZ.

    Дальше дорогу ведёт QuizDirector, а не StageDirector.
    """
    store = InMemorySessionStore()
    avatar = _FixedAvatar("реплика")
    sd = _StageDirectorStub([StageDecision(True, "training_understood", "stub")])
    runner = SessionRunner(
        fsm=FSMService(),
        store=store,
        avatar=avatar,
        stage_director=sd,
    )

    sid = uuid4()
    await store.save(
        sid,
        FSMState.TRAINING,
        SessionContext(employee_name="A", product_id="cc_novichok"),
    )

    res = await runner.dispatch(sid, UserMessage(text="понятно"))

    assert res.new_state is FSMState.TRAINING_QUIZ
    assert sd.calls == [FSMState.TRAINING]
    assert isinstance(res.effects[0], PersistSession)
    assert any(isinstance(e, EmitText) for e in res.effects)


@pytest.mark.asyncio
async def test_practice_refused_goes_through_eval_to_knowledge() -> None:
    store = InMemorySessionStore()
    sd = _StageDirectorStub([StageDecision(True, "practice_refused", "stub")])
    runner = SessionRunner(
        fsm=FSMService(),
        store=store,
        avatar=_FixedAvatar("r"),
        stage_director=sd,
        practice_evaluator=_AllWeakEvaluator(),
    )

    sid = uuid4()
    await store.save(
        sid,
        FSMState.PRACTICE,
        SessionContext(employee_name="A", product_id="cc_novichok"),
    )

    res = await runner.dispatch(sid, UserMessage(text="не хочу"))

    assert res.new_state is FSMState.KNOWLEDGE
    snap = await store.load(sid)
    assert snap is not None
    assert snap.ctx.weak_zones_remaining == ("needs", "pitch", "conditions")


@pytest.mark.asyncio
async def test_practice_accepted_finishes() -> None:
    store = InMemorySessionStore()

    class _NoWeak(PracticeEvaluator):
        async def evaluate(
            self,
            history: tuple[ChatMessage, ...],
            *,
            case_id: str | None = None,
        ) -> tuple[Zone, ...]:
            return ()

    sd = _StageDirectorStub([StageDecision(True, "practice_accepted", "stub")])
    runner = SessionRunner(
        fsm=FSMService(),
        store=store,
        avatar=_FixedAvatar("r"),
        stage_director=sd,
        practice_evaluator=_NoWeak(),
    )

    sid = uuid4()
    await store.save(
        sid,
        FSMState.PRACTICE,
        SessionContext(employee_name="A", product_id="cc_novichok"),
    )

    res = await runner.dispatch(sid, UserMessage(text="согласен оформить"))

    assert res.new_state is FSMState.FINISH


@pytest.mark.asyncio
async def test_continue_when_director_not_done() -> None:
    store = InMemorySessionStore()
    sd = _StageDirectorStub([StageDecision(False, "continue", "")])
    runner = SessionRunner(
        fsm=FSMService(),
        store=store,
        avatar=_FixedAvatar("r"),
        stage_director=sd,
    )

    sid = uuid4()
    await store.save(
        sid,
        FSMState.TRAINING,
        SessionContext(employee_name="A", product_id="cc_novichok"),
    )

    res = await runner.dispatch(sid, UserMessage(text="а что с лимитом?"))
    assert res.new_state is FSMState.TRAINING
