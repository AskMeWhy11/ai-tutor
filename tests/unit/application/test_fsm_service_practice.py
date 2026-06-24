"""FSMService: блок PRACTICE.

Покрывает:
* DialogDone: PRACTICE -> PRACTICE_EVAL.
* PracticeEvaluated: ветвление по weak_zones.
  - Пустой -> PRACTICE_SUCCESS, Mode.PRACTICE, weak_zones_remaining=().
  - Непустой -> PRACTICE_PARTIAL, weak_zones_remaining перезаписан.
* WeakZonesSent: PRACTICE_PARTIAL -> KNOWLEDGE.
* Валидацию состояний для всех трёх команд.
* E2E happy path: успех с первого круга.
* E2E partial path: один проход PRACTICE через PARTIAL до KNOWLEDGE.

Связанные документы:
    docs/FSM_INVARIANTS.md
    docs/adr/ADR-004-llm-verdict-as-fact.md
    docs/adr/ADR-005-no-cycle-limits.md
    docs/ROADMAP.md — Срез 1, Коммит 3
"""

from __future__ import annotations

import pytest

from application.commands import (
    DialogDone,
    PracticeEvaluated,
    WeakZonesSent,
)
from application.effects import PersistSession
from application.fsm_service import FSMService
from domain.context import SessionContext
from domain.states import FSMState, Mode

# ----------------------------------------------------------------------
# DialogDone
# ----------------------------------------------------------------------


class TestDialogDone:
    def test_practice_to_practice_eval(self) -> None:
        service = FSMService()
        ctx = SessionContext()

        result = service.handle(FSMState.PRACTICE, DialogDone(), ctx)

        assert result.new_state is FSMState.PRACTICE_EVAL
        assert result.new_ctx is ctx
        assert result.effects == (PersistSession(),)

    def test_invalid_state(self) -> None:
        service = FSMService()
        ctx = SessionContext()

        with pytest.raises(ValueError, match="DialogDone допустима только в PRACTICE"):
            service.handle(FSMState.PRACTICE_EVAL, DialogDone(), ctx)


# ----------------------------------------------------------------------
# PracticeEvaluated — ветка PARTIAL (HAS_FAILURES)
# ----------------------------------------------------------------------


class TestPracticeEvaluatedPartial:
    def test_non_empty_zones_to_partial(self) -> None:
        service = FSMService()
        ctx = SessionContext()

        result = service.handle(
            FSMState.PRACTICE_EVAL,
            PracticeEvaluated(weak_zones=("objection_handling",)),
            ctx,
        )

        assert result.new_state is FSMState.PRACTICE_PARTIAL
        assert result.effects == (PersistSession(),)

    def test_partial_writes_weak_zones(self) -> None:
        service = FSMService()
        ctx = SessionContext(weak_zones_remaining=())

        result = service.handle(
            FSMState.PRACTICE_EVAL,
            PracticeEvaluated(weak_zones=("a", "b", "c")),
            ctx,
        )

        assert result.new_ctx.weak_zones_remaining == ("a", "b", "c")

    def test_partial_overwrites_old_zones(self) -> None:
        """Зоны перезаписываются полностью, без слияния со старыми."""
        service = FSMService()
        ctx = SessionContext(weak_zones_remaining=("old_zone",))

        result = service.handle(
            FSMState.PRACTICE_EVAL,
            PracticeEvaluated(weak_zones=("new_zone",)),
            ctx,
        )

        assert result.new_ctx.weak_zones_remaining == ("new_zone",)

    def test_partial_does_not_mark_practice_complete(self) -> None:
        service = FSMService()
        ctx = SessionContext(
            completed_modes=frozenset({Mode.TRAINING, Mode.EXAMPLE}),
        )

        result = service.handle(
            FSMState.PRACTICE_EVAL,
            PracticeEvaluated(weak_zones=("z",)),
            ctx,
        )

        assert Mode.PRACTICE not in result.new_ctx.completed_modes


# ----------------------------------------------------------------------
# PracticeEvaluated — ветка SUCCESS (ALL_ZONES_OK)
# ----------------------------------------------------------------------


class TestPracticeEvaluatedSuccess:
    def test_empty_zones_to_success(self) -> None:
        service = FSMService()
        ctx = SessionContext()

        result = service.handle(
            FSMState.PRACTICE_EVAL,
            PracticeEvaluated(weak_zones=()),
            ctx,
        )

        assert result.new_state is FSMState.PRACTICE_SUCCESS
        assert result.effects == (PersistSession(),)

    def test_success_marks_practice_complete(self) -> None:
        service = FSMService()
        ctx = SessionContext(completed_modes=frozenset())

        result = service.handle(
            FSMState.PRACTICE_EVAL,
            PracticeEvaluated(weak_zones=()),
            ctx,
        )

        assert Mode.PRACTICE in result.new_ctx.completed_modes

    def test_success_clears_weak_zones(self) -> None:
        """Защитная перезапись: успех гарантированно занулит зоны,
        даже если по какой-то причине в ctx остались старые.
        """
        service = FSMService()
        ctx = SessionContext(weak_zones_remaining=("stale",))

        result = service.handle(
            FSMState.PRACTICE_EVAL,
            PracticeEvaluated(weak_zones=()),
            ctx,
        )

        assert result.new_ctx.weak_zones_remaining == ()

    def test_success_keeps_knowledge_locked_when_no_zones(self) -> None:
        """Тонкость модели: PRACTICE пройден на отлично -> зон нет ->
        KNOWLEDGE остаётся недоступен (нечего прокачивать).
        """
        service = FSMService()
        ctx = SessionContext()

        result = service.handle(
            FSMState.PRACTICE_EVAL,
            PracticeEvaluated(weak_zones=()),
            ctx,
        )

        assert result.new_ctx.knowledge_unlocked is False

    def test_success_preserves_other_completed_modes(self) -> None:
        service = FSMService()
        ctx = SessionContext(
            completed_modes=frozenset({Mode.TRAINING, Mode.EXAMPLE}),
        )

        result = service.handle(
            FSMState.PRACTICE_EVAL,
            PracticeEvaluated(weak_zones=()),
            ctx,
        )

        assert result.new_ctx.completed_modes == frozenset(
            {Mode.TRAINING, Mode.EXAMPLE, Mode.PRACTICE},
        )

    def test_success_idempotent(self) -> None:
        service = FSMService()
        ctx = SessionContext(
            completed_modes=frozenset({Mode.PRACTICE}),
        )

        result = service.handle(
            FSMState.PRACTICE_EVAL,
            PracticeEvaluated(weak_zones=()),
            ctx,
        )

        assert result.new_ctx.completed_modes == frozenset({Mode.PRACTICE})
        assert result.new_state is FSMState.PRACTICE_SUCCESS


class TestPracticeEvaluatedValidation:
    def test_invalid_state(self) -> None:
        service = FSMService()
        ctx = SessionContext()

        with pytest.raises(
            ValueError,
            match="PracticeEvaluated допустима только в PRACTICE_EVAL",
        ):
            service.handle(
                FSMState.PRACTICE,
                PracticeEvaluated(weak_zones=()),
                ctx,
            )


# ----------------------------------------------------------------------
# WeakZonesSent
# ----------------------------------------------------------------------


class TestWeakZonesSent:
    def test_partial_to_knowledge(self) -> None:
        service = FSMService()
        ctx = SessionContext(weak_zones_remaining=("a", "b"))

        result = service.handle(FSMState.PRACTICE_PARTIAL, WeakZonesSent(), ctx)

        assert result.new_state is FSMState.KNOWLEDGE
        assert result.effects == (PersistSession(),)

    def test_does_not_mutate_ctx(self) -> None:
        """Зоны уже записаны на шаге PracticeEvaluated.
        WeakZonesSent — это чистый переход без мутаций.
        """
        service = FSMService()
        ctx = SessionContext(
            completed_modes=frozenset({Mode.TRAINING, Mode.EXAMPLE}),
            weak_zones_remaining=("a", "b"),
        )

        result = service.handle(FSMState.PRACTICE_PARTIAL, WeakZonesSent(), ctx)

        assert result.new_ctx is ctx

    def test_invalid_state(self) -> None:
        service = FSMService()
        ctx = SessionContext()

        with pytest.raises(
            ValueError,
            match="WeakZonesSent допустима только в PRACTICE_PARTIAL",
        ):
            service.handle(FSMState.PRACTICE, WeakZonesSent(), ctx)


# ----------------------------------------------------------------------
# E2E happy path: успех с первого подхода
# ----------------------------------------------------------------------


class TestPracticeHappyPath:
    def test_first_attempt_success(self) -> None:
        service = FSMService()
        state = FSMState.PRACTICE
        ctx = SessionContext(
            completed_modes=frozenset({Mode.TRAINING, Mode.EXAMPLE}),
        )

        # Диалог завершён -> EVAL
        result = service.handle(state, DialogDone(), ctx)
        state, ctx = result.new_state, result.new_ctx
        assert state is FSMState.PRACTICE_EVAL

        # LLM: зон нет -> SUCCESS
        result = service.handle(state, PracticeEvaluated(weak_zones=()), ctx)
        state, ctx = result.new_state, result.new_ctx
        assert state is FSMState.PRACTICE_SUCCESS
        assert ctx.completed_modes == frozenset(
            {Mode.TRAINING, Mode.EXAMPLE, Mode.PRACTICE},
        )
        assert ctx.weak_zones_remaining == ()
        assert ctx.knowledge_unlocked is False  # нечего прокачивать


# ----------------------------------------------------------------------
# E2E partial path: один проход PRACTICE до KNOWLEDGE через PARTIAL
# ----------------------------------------------------------------------


class TestPracticePartialPath:
    """Сценарий с провалом части зон: PRACTICE -> EVAL -> PARTIAL -> KNOWLEDGE.

    REPEAT_CYCLE и инкремент cycle_count относятся к KNOWLEDGE-блоку
    и проверяются в Коммите 4.
    """

    def test_practice_to_knowledge_via_partial(self) -> None:
        service = FSMService()
        state = FSMState.PRACTICE
        ctx = SessionContext(
            completed_modes=frozenset({Mode.TRAINING, Mode.EXAMPLE}),
        )

        # Диалог завершён -> EVAL
        result = service.handle(state, DialogDone(), ctx)
        state, ctx = result.new_state, result.new_ctx
        assert state is FSMState.PRACTICE_EVAL

        # LLM: есть провалы -> PARTIAL, зоны записаны в ctx
        result = service.handle(
            state,
            PracticeEvaluated(weak_zones=("greeting", "needs_discovery")),
            ctx,
        )
        state, ctx = result.new_state, result.new_ctx
        assert state is FSMState.PRACTICE_PARTIAL
        assert ctx.weak_zones_remaining == ("greeting", "needs_discovery")
        assert Mode.PRACTICE not in ctx.completed_modes

        # Зоны переданы -> KNOWLEDGE, ctx сохраняет зоны
        result = service.handle(state, WeakZonesSent(), ctx)
        state, ctx = result.new_state, result.new_ctx
        assert state is FSMState.KNOWLEDGE
        assert ctx.weak_zones_remaining == ("greeting", "needs_discovery")

    def test_eval_overwrites_zones_on_repeat(self) -> None:
        """Повторный проход EVAL перезаписывает зоны без слияния.

        Сценарий важен для Коммита 4 (REPEAT_CYCLE), но проверяем
        контракт перезаписи уже сейчас, на уровне самого EVAL.
        """
        service = FSMService()
        ctx = SessionContext(weak_zones_remaining=("old_a", "old_b"))

        result = service.handle(
            FSMState.PRACTICE_EVAL,
            PracticeEvaluated(weak_zones=("new_c",)),
            ctx,
        )

        assert result.new_ctx.weak_zones_remaining == ("new_c",)
