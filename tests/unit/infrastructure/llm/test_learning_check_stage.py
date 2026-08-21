"""Тесты v10: LEARNING_CHECK — этап TRAINING (эталон: WELCOME→LEARNING→LEARNING_CHECK)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from domain.context import SessionContext
from domain.states import FSMState, Mode
from domain.types import ChatMessage
from infrastructure.content.registry import DEFAULT_CASE_ID
from infrastructure.llm.content_render import apply_step
from infrastructure.llm.prompt_store import PromptStore
from infrastructure.llm.training_steps import training_step
from infrastructure.llm.variables import resolve_variable
from infrastructure.llm.yaml_export import export_prompts_yaml

pytestmark = pytest.mark.unit


# ---------- {STEP}: вычисление и подстановка ----------


def test_training_step_welcome_learning_check() -> None:
    empty = SessionContext()
    assert training_step(FSMState.TRAINING, empty) == "WELCOME"
    with_user = SessionContext(dialog_history=(ChatMessage(role="user", text="привет"),))
    assert training_step(FSMState.TRAINING, with_user) == "LEARNING"
    assert training_step(FSMState.TRAINING_QUIZ, with_user) == "LEARNING_CHECK"
    assert training_step(FSMState.TRAINING_EXPLAIN, with_user) == "LEARNING_CHECK"


def test_apply_step_substitutes() -> None:
    out = apply_step(
        "Этап: {STEP}, статус: {STEP_STATUS}", "LEARNING_CHECK", "LEARNING_CHECK_STARTED"
    )
    assert out == "Этап: LEARNING_CHECK, статус: LEARNING_CHECK_STARTED"
    # Прочие скобки не трогаются.
    assert apply_step('{"json": 1} {STEP}', "LEARNING") == '{"json": 1} LEARNING'


def test_training_prompt_has_step_sections(tmp_path: Path) -> None:
    store = PromptStore(tmp_path / "prompts.json")
    text = store.get_mode_prompt(Mode.TRAINING, DEFAULT_CASE_ID)
    for section in ("=== ЭТАП WELCOME", "=== ЭТАП LEARNING (", "=== ЭТАП LEARNING_CHECK"):
        assert section in text
    # {STEP} остаётся до вызова (контекстный), контентные — подставлены.
    assert "{STEP}" in text
    assert "{LEARNING_CHECK_LIST}" not in text
    assert "{COUNT_OF_QUESTIONS}" not in text


# ---------- переменные ----------


def test_learning_check_variables() -> None:
    lst = resolve_variable("learning-check-list", DEFAULT_CASE_ID)
    assert lst.strip()
    count = resolve_variable("count-of-questions", DEFAULT_CASE_ID)
    assert count.isdigit() and int(count) >= 1


# ---------- SD TRAINING: статусы LEARNING_CHECK ----------


def test_sd_training_has_learning_check_statuses(tmp_path: Path) -> None:
    store = PromptStore(tmp_path / "prompts.json")
    sd = store.get_stage_director_prompt(Mode.TRAINING, DEFAULT_CASE_ID)
    for token in (
        "LEARNING_CHECK_STARTED",
        "LEARNING_CHECK_FINISHED_SUCCESS",
        "LEARNING_CHECK_FINISHED_FAILED",
        "learning_check_finished_success",
        "learning_check_finished_failed",
    ):
        assert token in sd
    # Другие судьи статусов квиза не содержат.
    assert "LEARNING_CHECK_FINISHED" not in store.get_stage_director_prompt(
        Mode.PRACTICE, DEFAULT_CASE_ID
    )


# ---------- runner: сквозной flow LEARNING_CHECK → EXAMPLE ----------


async def test_training_flow_through_learning_check() -> None:
    from uuid import uuid4

    from application.commands import UserMessage
    from application.fsm_service import FSMService
    from application.ports.stage_director import StageDecision
    from application.session_runner import SessionRunner
    from tests.fakes.in_memory_session_store import InMemorySessionStore

    class _ScriptedDirector:
        """TRAINING закрывает после 1-й реплики, квиз — после 2-х ответов."""

        async def decide(self, *, state: FSMState, ctx: SessionContext) -> StageDecision:
            user_turns = sum(1 for m in ctx.dialog_history if m.role == "user")
            if state is FSMState.TRAINING and user_turns >= 1:
                return StageDecision(True, "training_understood", "t")
            if state is FSMState.TRAINING_QUIZ and user_turns >= 3:
                return StageDecision(True, "learning_check_finished_success", "q")
            return StageDecision(False, "continue", "")

    class _Avatar:
        async def next_message(self, state: FSMState, ctx: SessionContext) -> str:
            return f"MSG:{state.value}"

        async def next_hint(self, state: FSMState, ctx: SessionContext) -> str | None:
            return None

    store = InMemorySessionStore()
    sid = uuid4()
    await store.save(sid, FSMState.TRAINING, SessionContext(product_id="cc_novichok"))
    runner = SessionRunner(
        fsm=FSMService(),
        store=store,
        avatar=_Avatar(),
        stage_director=_ScriptedDirector(),
    )

    # 1-я реплика: теория закрыта → TRAINING_QUIZ (этап LEARNING_CHECK).
    await runner.dispatch(sid, UserMessage(text="понятно"))
    snap = await store.load(sid)
    assert snap is not None and snap.state is FSMState.TRAINING_QUIZ
    # Диалог единый: история не обнулилась и содержит реплику сотрудника.
    assert any(m.role == "user" for m in snap.ctx.dialog_history)

    # Ответы квиза — обычные текстовые реплики того же диалога.
    await runner.dispatch(sid, UserMessage(text="ответ 1"))
    snap = await store.load(sid)
    assert snap is not None and snap.state is FSMState.TRAINING_QUIZ

    result = await runner.dispatch(sid, UserMessage(text="ответ 2"))
    snap = await store.load(sid)
    assert snap is not None and snap.state is FSMState.EXAMPLE
    assert result.new_state is FSMState.EXAMPLE


# ---------- миграция v9 → v10 ----------


def test_v9_quiz_prompt_merged_into_training(tmp_path: Path) -> None:
    payload = {
        "version": 9,
        "system_prompt": "",
        "templates": {},
        "cases": {
            "xpv": {
                "mode_prompts": {"training": "CUSTOM TRAINING TEXT"},
                "quiz_prompt": "CUSTOM QUIZ RULES",
            }
        },
    }
    path = tmp_path / "prompts.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    store = PromptStore(path)
    training = store.snapshot("xpv").mode_prompts[Mode.TRAINING]
    # Оба контента сохранены в одном промпте.
    assert "CUSTOM TRAINING TEXT" in training
    assert "CUSTOM QUIZ RULES" in training
    assert "=== ЭТАП LEARNING_CHECK" in training
    # Ключ квиза из хранилища удалён.
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["version"] == 10
    assert "quiz_prompt" not in raw["cases"]["xpv"]


# ---------- YAML: ключа квиза нет ----------


def test_yaml_export_has_no_quiz_key(tmp_path: Path) -> None:
    store = PromptStore(tmp_path / "prompts.json")
    out = export_prompts_yaml(store, DEFAULT_CASE_ID)
    assert "-learning-quiz-transcription-prompt:" not in out
    assert "ЭТАП LEARNING_CHECK" in out  # квиз внутри learning-transcription
