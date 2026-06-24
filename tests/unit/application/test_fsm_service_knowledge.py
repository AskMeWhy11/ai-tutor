"""FSMService: блок KNOWLEDGE и финал.

Покрывает:
* ZonesDone: KNOWLEDGE -> KNOWLEDGE_DONE, обнуление weak_zones_remaining.
* RepeatCycle: KNOWLEDGE_DONE -> EXAMPLE, инкремент cycle_count.
* Continue из PRACTICE_SUCCESS -> FINISH (без мутаций).
* Валидация состояний для всех трёх команд.
* E2E полная петля: PRACTICE -> PARTIAL -> KNOWLEDGE -> KNOWLEDGE_DONE
  -> EXAMPLE -> PRACTICE -> SUCCESS -> FINISH.

Связанные документы:
    docs/FSM_INVARIANTS.md
    docs/adr/ADR-005-no-cycle-limits.md
    docs/ROADMAP.md — Срез 1, Коммит 4
"""

from __future__ import annotations

import pytest

from application.commands import (
    Continue,
    DialogDone,
    PracticeEvaluated,
    RepeatCycle,
    ScenarioDone,
    WeakZonesSent,
    ZonesDone,
)
from application.effects import PersistSession
from application.fsm_service import FSMService
from domain.context import SessionContext
from domain.states import FSMState, Mode

# ----------------------------------------------------------------------
# ZonesDone
# ----------------------------------------------------------------------


class TestZonesDone:
    def test_knowledge_to_knowledge_done(self) -> None:
        service = FSMService()
        ctx = SessionContext(weak_zones_remaining=("a", "b"))

        result = service.handle(FSMState.KNOWLEDGE, ZonesDone(), ctx)

        assert result.new_state is FSMState.KNOWLEDGE_DONE
        assert result.effects == (PersistSession(),)

    def test_clears_weak_zones(self) -> None:
        service = FSMService()
        ctx = SessionContext(weak_zones_remaining=("a", "b", "c"))

        result = service.handle(FSMState.KNOWLEDGE, ZonesDone(), ctx)

        assert result.new_ctx.weak_zones_remaining == ()

    def test_clears_even_if_already_empty(self) -> None:
        """Идемпотентность: повторный ZonesDone не падает.
        В реальной FSM этот сценарий невозможен (PRACTICE_PARTIAL -> KNOWLEDGE
        требует непустых зон), но защитный инвариант полезен.
        """
        service = FSMService()
        ctx = SessionContext(weak_zones_remaining=())

        result = service.handle(FSMState.KNOWLEDGE, ZonesDone(), ctx)

        assert result.new_ctx.weak_zones_remaining == ()

    def test_does_not_touch_other_fields(self) -> None:
        service = FSMService()
        ctx = SessionContext(
            completed_modes=frozenset({Mode.TRAINING, Mode.EXAMPLE}),
            weak_zones_remaining=("z",),
            cycle_count=2,
        )

        result = service.handle(FSMState.KNOWLEDGE, ZonesDone(), ctx)

        # ZonesDone семантически означает «KNOWLEDGE завершён», поэтому Mode.KNOWLEDGE
        # обязан появиться в completed_modes.
        assert result.new_ctx.completed_modes == frozenset(
            {Mode.TRAINING, Mode.EXAMPLE, Mode.KNOWLEDGE},
        )
        assert result.new_ctx.cycle_count == 2

    def test_invalid_state(self) -> None:
        service = FSMService()
        ctx = SessionContext()

        with pytest.raises(
            ValueError,
            match="ZonesDone допустима только в KNOWLEDGE",
        ):
            service.handle(FSMState.KNOWLEDGE_DONE, ZonesDone(), ctx)


# ----------------------------------------------------------------------
# RepeatCycle
# ----------------------------------------------------------------------


class TestRepeatCycle:
    def test_knowledge_done_to_example(self) -> None:
        service = FSMService()
        ctx = SessionContext()

        result = service.handle(FSMState.KNOWLEDGE_DONE, RepeatCycle(), ctx)

        assert result.new_state is FSMState.EXAMPLE
        assert result.effects == (PersistSession(),)

    def test_increments_cycle_count(self) -> None:
        service = FSMService()
        ctx = SessionContext(cycle_count=0)

        result = service.handle(FSMState.KNOWLEDGE_DONE, RepeatCycle(), ctx)

        assert result.new_ctx.cycle_count == 1

    def test_increments_from_non_zero(self) -> None:
        service = FSMService()
        ctx = SessionContext(cycle_count=3)

        result = service.handle(FSMState.KNOWLEDGE_DONE, RepeatCycle(), ctx)

        assert result.new_ctx.cycle_count == 4

    def test_no_cycle_limit(self) -> None:
        """ADR-005: счётчик растёт без потолка."""
        service = FSMService()
        ctx = SessionContext(cycle_count=999)

        result = service.handle(FSMState.KNOWLEDGE_DONE, RepeatCycle(), ctx)

        assert result.new_ctx.cycle_count == 1000
        assert result.new_state is FSMState.EXAMPLE

    def test_does_not_touch_other_fields(self) -> None:
        service = FSMService()
        ctx = SessionContext(
            completed_modes=frozenset({Mode.TRAINING, Mode.EXAMPLE, Mode.PRACTICE}),
            weak_zones_remaining=(),
            cycle_count=1,
        )

        result = service.handle(FSMState.KNOWLEDGE_DONE, RepeatCycle(), ctx)

        assert result.new_ctx.completed_modes == frozenset(
            {Mode.TRAINING, Mode.EXAMPLE, Mode.PRACTICE},
        )
        assert result.new_ctx.weak_zones_remaining == ()

    def test_invalid_state(self) -> None:
        service = FSMService()
        ctx = SessionContext()

        with pytest.raises(
            ValueError,
            match="RepeatCycle допустима только в KNOWLEDGE_DONE",
        ):
            service.handle(FSMState.KNOWLEDGE, RepeatCycle(), ctx)


# ----------------------------------------------------------------------
# Continue из PRACTICE_SUCCESS
# ----------------------------------------------------------------------


class TestContinueFromPracticeSuccess:
    def test_practice_success_to_finish(self) -> None:
        service = FSMService()
        ctx = SessionContext(completed_modes=frozenset({Mode.PRACTICE}))

        result = service.handle(FSMState.PRACTICE_SUCCESS, Continue(), ctx)

        assert result.new_state is FSMState.FINISH
        assert result.effects == (PersistSession(),)

    def test_does_not_mutate_ctx(self) -> None:
        service = FSMService()
        ctx = SessionContext(
            completed_modes=frozenset({Mode.TRAINING, Mode.EXAMPLE, Mode.PRACTICE}),
            cycle_count=2,
        )

        result = service.handle(FSMState.PRACTICE_SUCCESS, Continue(), ctx)

        assert result.new_ctx is ctx


# ----------------------------------------------------------------------
# E2E: полная петля с одним повторением
# ----------------------------------------------------------------------


class TestFullCyclePath:
    """PRACTICE проваливается -> KNOWLEDGE -> новая петля -> SUCCESS -> FINISH."""

    def test_one_full_cycle_then_success(self) -> None:
        service = FSMService()
        state = FSMState.PRACTICE
        ctx = SessionContext(
            completed_modes=frozenset({Mode.TRAINING, Mode.EXAMPLE}),
        )

        # Круг 1: PRACTICE -> EVAL -> PARTIAL -> KNOWLEDGE
        result = service.handle(state, DialogDone(), ctx)
        state, ctx = result.new_state, result.new_ctx

        result = service.handle(
            state,
            PracticeEvaluated(weak_zones=("greeting",)),
            ctx,
        )
        state, ctx = result.new_state, result.new_ctx
        assert state is FSMState.PRACTICE_PARTIAL
        assert ctx.weak_zones_remaining == ("greeting",)

        result = service.handle(state, WeakZonesSent(), ctx)
        state, ctx = result.new_state, result.new_ctx
        assert state is FSMState.KNOWLEDGE

        # KNOWLEDGE -> KNOWLEDGE_DONE: зоны проработаны
        result = service.handle(state, ZonesDone(), ctx)
        state, ctx = result.new_state, result.new_ctx
        assert state is FSMState.KNOWLEDGE_DONE
        assert ctx.weak_zones_remaining == ()
        assert ctx.cycle_count == 0  # ещё не начали повтор

        # KNOWLEDGE_DONE -> EXAMPLE: повтор петли
        result = service.handle(state, RepeatCycle(), ctx)
        state, ctx = result.new_state, result.new_ctx
        assert state is FSMState.EXAMPLE
        assert ctx.cycle_count == 1

        # EXAMPLE -> EXAMPLE_DONE -> PRACTICE
        result = service.handle(state, ScenarioDone(), ctx)
        state, ctx = result.new_state, result.new_ctx
        assert state is FSMState.EXAMPLE_DONE

        result = service.handle(state, Continue(), ctx)
        state, ctx = result.new_state, result.new_ctx
        assert state is FSMState.PRACTICE

        # Круг 2: PRACTICE -> EVAL -> SUCCESS
        result = service.handle(state, DialogDone(), ctx)
        state, ctx = result.new_state, result.new_ctx

        result = service.handle(state, PracticeEvaluated(weak_zones=()), ctx)
        state, ctx = result.new_state, result.new_ctx
        assert state is FSMState.PRACTICE_SUCCESS
        assert Mode.PRACTICE in ctx.completed_modes
        assert ctx.cycle_count == 1

        # PRACTICE_SUCCESS -> FINISH
        result = service.handle(state, Continue(), ctx)
        state, ctx = result.new_state, result.new_ctx
        assert state is FSMState.FINISH
        assert ctx.cycle_count == 1

    def test_multiple_partial_cycles(self) -> None:
        """ADR-005: можно повторять прокачку сколько угодно раз."""
        service = FSMService()
        ctx = SessionContext()

        # Имитируем 3 завершения KNOWLEDGE_DONE подряд
        for expected in range(1, 4):
            result = service.handle(FSMState.KNOWLEDGE_DONE, RepeatCycle(), ctx)
            ctx = result.new_ctx
            assert ctx.cycle_count == expected
