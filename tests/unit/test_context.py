"""Тесты для domain.context.SessionContext."""

from __future__ import annotations

import dataclasses

import pytest

from domain.context import SessionContext
from domain.states import FSMState, Mode


@pytest.mark.unit
class TestSessionContextDefaults:
    def test_default_construction(self) -> None:
        ctx = SessionContext()

        assert ctx.has_active_session is False
        assert ctx.employee_name == ""
        assert ctx.product_id == ""
        assert ctx.completed_modes == frozenset()
        assert ctx.weak_zones_remaining == ()
        assert ctx.cycle_count == 0
        assert ctx.quiz_question_index == 0
        assert ctx.last_answer_correct is None
        assert ctx.saved_state is None

    def test_is_frozen(self) -> None:
        ctx = SessionContext()
        with pytest.raises(dataclasses.FrozenInstanceError):
            ctx.cycle_count = 1  # type: ignore[misc]


@pytest.mark.unit
class TestKnowledgeUnlocked:
    def test_locked_when_practice_not_completed(self) -> None:
        ctx = SessionContext(
            completed_modes=frozenset({Mode.TRAINING}),
            weak_zones_remaining=("greeting",),
        )
        assert ctx.knowledge_unlocked is False

    def test_locked_when_no_weak_zones(self) -> None:
        ctx = SessionContext(
            completed_modes=frozenset({Mode.PRACTICE}),
            weak_zones_remaining=(),
        )
        assert ctx.knowledge_unlocked is False

    def test_unlocked_when_practice_done_and_weak_zones_present(self) -> None:
        ctx = SessionContext(
            completed_modes=frozenset({Mode.PRACTICE}),
            weak_zones_remaining=("greeting", "needs_analysis"),
        )
        assert ctx.knowledge_unlocked is True


@pytest.mark.unit
class TestSavedState:
    def test_saved_state_can_be_any_fsm_state(self) -> None:
        for state in FSMState:
            ctx = SessionContext(saved_state=state)
            assert ctx.saved_state is state
