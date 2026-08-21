"""Тесты SessionRunner."""

from __future__ import annotations

from uuid import uuid4

import pytest

from application.commands import SelectMode, StartSession, StartTraining, UserMessage
from application.effects import EmitHint, EmitText, PersistSession, PlayAudio
from application.fsm_service import FSMService
from application.session_runner import SessionRunner
from domain.context import SessionContext
from domain.states import FSMState
from tests.fakes.in_memory_session_store import InMemorySessionStore


class _FakeAvatar:
    def __init__(self, message: str = "Hello") -> None:
        self.message = message
        self.calls: list[tuple[FSMState, SessionContext]] = []

    async def next_message(self, state: FSMState, ctx: SessionContext) -> str:
        self.calls.append((state, ctx))
        return self.message

    async def next_hint(self, state: FSMState, ctx: SessionContext) -> str | None:
        return None


class _StateAwareAvatar:
    """Аватар, чей текст зависит от состояния — удобно считать дубли."""

    async def next_message(self, state: FSMState, ctx: SessionContext) -> str:
        return f"MSG:{state.value}"

    async def next_hint(self, state: FSMState, ctx: SessionContext) -> str | None:
        return None


class _FakeTTS:
    extension = "wav"
    mime = "audio/wav"

    def __init__(self, audio: bytes | None = b"PCM") -> None:
        self.audio = audio

    async def synthesize(self, text: str) -> bytes | None:
        return self.audio


class _FakeCache:
    def __init__(self) -> None:
        self.put_calls: list[tuple[bytes, str]] = []

    async def put(self, audio: bytes, ext: str) -> str:
        self.put_calls.append((audio, ext))
        return "fake-key"


@pytest.mark.asyncio
async def test_dispatch_emits_avatar_text_for_initial_state() -> None:
    runner = SessionRunner(
        fsm=FSMService(),
        store=InMemorySessionStore(),
        avatar=_FakeAvatar("Привет!"),
    )
    sid = uuid4()
    result = await runner.dispatch(sid, StartSession())

    texts = [e for e in result.effects if isinstance(e, EmitText)]
    assert any(e.text == "Привет!" for e in texts)


@pytest.mark.asyncio
async def test_dispatch_persists_when_persist_effect_present() -> None:
    store = InMemorySessionStore()
    runner = SessionRunner(fsm=FSMService(), store=store, avatar=_FakeAvatar())
    sid = uuid4()
    result = await runner.dispatch(sid, StartSession())

    assert any(isinstance(e, PersistSession) for e in result.effects)
    snap = await store.load(sid)
    assert snap is not None


@pytest.mark.asyncio
async def test_dispatch_handles_avatar_failure_gracefully() -> None:
    class Boom:
        async def next_message(self, state: FSMState, ctx: SessionContext) -> str:
            raise RuntimeError("LLM down")

        async def next_hint(self, state: FSMState, ctx: SessionContext) -> str | None:
            return None

    runner = SessionRunner(fsm=FSMService(), store=InMemorySessionStore(), avatar=Boom())
    result = await runner.dispatch(uuid4(), StartSession())
    # FSM отработал, EmitText от аватара отсутствует.
    assert all(not isinstance(e, EmitText) for e in result.effects)


@pytest.mark.asyncio
async def test_dispatch_emits_play_audio_when_tts_returns_bytes() -> None:
    cache = _FakeCache()
    runner = SessionRunner(
        fsm=FSMService(),
        store=InMemorySessionStore(),
        avatar=_FakeAvatar("Hi"),
        tts=_FakeTTS(audio=b"AUDIO"),
        audio_cache=cache,
    )
    result = await runner.dispatch(uuid4(), StartSession())
    assert any(isinstance(e, PlayAudio) for e in result.effects)
    assert cache.put_calls == [(b"AUDIO", "wav")]


@pytest.mark.asyncio
async def test_dispatch_no_play_audio_when_tts_returns_none() -> None:
    runner = SessionRunner(
        fsm=FSMService(),
        store=InMemorySessionStore(),
        avatar=_FakeAvatar("Hi"),
        tts=_FakeTTS(audio=None),
        audio_cache=_FakeCache(),
    )
    result = await runner.dispatch(uuid4(), StartSession())
    assert all(not isinstance(e, PlayAudio) for e in result.effects)


@pytest.mark.asyncio
async def test_full_training_flow_via_runner() -> None:
    runner = SessionRunner(
        fsm=FSMService(),
        store=InMemorySessionStore(),
        avatar=_FakeAvatar(),
    )
    sid = uuid4()
    await runner.dispatch(sid, StartSession())
    res = await runner.dispatch(sid, StartTraining(employee_name="A", product_id="cc_novichok"))
    assert res.new_state is FSMState.WELCOME
    res = await runner.dispatch(sid, SelectMode(mode="training"))
    assert res.new_state is FSMState.TRAINING


@pytest.mark.asyncio
async def test_dispatch_without_avatar_yields_no_emit_text() -> None:
    runner = SessionRunner(fsm=FSMService(), store=InMemorySessionStore(), avatar=None)
    result = await runner.dispatch(uuid4(), StartSession())
    assert all(not isinstance(e, EmitText) for e in result.effects)


@pytest.mark.asyncio
async def test_learning_check_close_emits_training_done_reply_once() -> None:
    # Этап LEARNING_CHECK закрывает StageDirector: TRAINING_QUIZ → TRAINING_DONE
    # → EXAMPLE; реплика TRAINING_DONE уходит ровно один раз.
    from application.ports.stage_director import StageDecision

    class _QuizDoneDirector:
        async def decide(self, *, state: FSMState, ctx: SessionContext) -> StageDecision:
            if state is FSMState.TRAINING_QUIZ:
                return StageDecision(True, "learning_check_finished_success", "test")
            return StageDecision(False, "continue", "")

    store = InMemorySessionStore()
    sid = uuid4()
    await store.save(
        sid,
        FSMState.TRAINING_QUIZ,
        SessionContext(product_id="xpv", quiz_question_index=0),
    )
    runner = SessionRunner(
        fsm=FSMService(),
        store=store,
        avatar=_StateAwareAvatar(),
        stage_director=_QuizDoneDirector(),
    )

    result = await runner.dispatch(sid, UserMessage(text="мой ответ"))

    done_msgs = [
        e for e in result.effects if isinstance(e, EmitText) and e.text == "MSG:TRAINING_DONE"
    ]
    assert len(done_msgs) == 1, [e.text for e in result.effects if isinstance(e, EmitText)]
    snap = await store.load(sid)
    assert snap is not None and snap.state is FSMState.EXAMPLE


@pytest.mark.asyncio
async def test_example_hint_only_for_cc_novichok() -> None:
    # Подсказка «📌 …» (rationale cc_novichok) не должна показываться для
    # техник продаж.
    cc_hint = SessionRunner._build_hint(FSMState.EXAMPLE, SessionContext(product_id="cc_novichok"))
    assert isinstance(cc_hint, EmitHint)

    for pid in ("xpv", "spin", "pusk", "aida", "storytelling"):
        assert SessionRunner._build_hint(FSMState.EXAMPLE, SessionContext(product_id=pid)) is None
