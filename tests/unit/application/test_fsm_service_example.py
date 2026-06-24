"""FSMService: блок EXAMPLE (ScenarioDone, Continue из EXAMPLE_DONE).

Покрывает:
* EXAMPLE -> EXAMPLE_DONE при ScenarioDone, с фиксацией Mode.EXAMPLE.
* EXAMPLE_DONE -> PRACTICE при Continue.
* Валидацию состояния для обеих команд.
* E2E happy path: TRAINING -> ... -> EXAMPLE -> EXAMPLE_DONE -> PRACTICE.

Связанные документы:
    docs/FSM_INVARIANTS.md — таблица мутаций
    docs/ROADMAP.md — Срез 1, Коммит 2
"""

from __future__ import annotations

import pytest

from application.commands import (
    Continue,
    ScenarioDone,
    SubmitQuizAnswer,
    TheoryDone,
)
from application.effects import PersistSession
from application.fsm_service import FSMService
from domain.constants import TRAINING_QUIZ_QUESTIONS
from domain.context import SessionContext
from domain.states import FSMState, Mode

# ----------------------------------------------------------------------
# ScenarioDone
# ----------------------------------------------------------------------


class TestScenarioDone:
    def test_example_to_example_done(self) -> None:
        service = FSMService()
        ctx = SessionContext()

        result = service.handle(FSMState.EXAMPLE, ScenarioDone(), ctx)

        assert result.new_state is FSMState.EXAMPLE_DONE
        assert result.effects == (PersistSession(),)

    def test_marks_example_complete(self) -> None:
        service = FSMService()
        ctx = SessionContext(completed_modes=frozenset())

        result = service.handle(FSMState.EXAMPLE, ScenarioDone(), ctx)

        assert Mode.EXAMPLE in result.new_ctx.completed_modes

    def test_preserves_other_completed_modes(self) -> None:
        """Сценарий: пользователь прошёл TRAINING, потом EXAMPLE.
        В completed_modes должны быть оба режима.
        """
        service = FSMService()
        ctx = SessionContext(completed_modes=frozenset({Mode.TRAINING}))

        result = service.handle(FSMState.EXAMPLE, ScenarioDone(), ctx)

        assert result.new_ctx.completed_modes == frozenset({Mode.TRAINING, Mode.EXAMPLE})

    def test_idempotent_when_example_already_complete(self) -> None:
        """Сценарий восстановления: если Mode.EXAMPLE уже стоит,
        повторное проставление не должно ничего сломать.
        """
        service = FSMService()
        ctx = SessionContext(completed_modes=frozenset({Mode.EXAMPLE}))

        result = service.handle(FSMState.EXAMPLE, ScenarioDone(), ctx)

        assert result.new_ctx.completed_modes == frozenset({Mode.EXAMPLE})
        assert result.new_state is FSMState.EXAMPLE_DONE

    def test_does_not_touch_other_fields(self) -> None:
        service = FSMService()
        ctx = SessionContext(
            employee_name="Анна",
            product_id="kasko",
            quiz_question_index=3,
            last_answer_correct=True,
            cycle_count=1,
        )

        result = service.handle(FSMState.EXAMPLE, ScenarioDone(), ctx)

        assert result.new_ctx.employee_name == "Анна"
        assert result.new_ctx.product_id == "kasko"
        assert result.new_ctx.quiz_question_index == 3
        assert result.new_ctx.last_answer_correct is True
        assert result.new_ctx.cycle_count == 1

    def test_invalid_state(self) -> None:
        service = FSMService()
        ctx = SessionContext()

        with pytest.raises(ValueError, match="ScenarioDone допустима только в EXAMPLE"):
            service.handle(FSMState.EXAMPLE_DONE, ScenarioDone(), ctx)


# ----------------------------------------------------------------------
# Continue из EXAMPLE_DONE
# ----------------------------------------------------------------------


class TestContinueFromExampleDone:
    def test_example_done_to_practice(self) -> None:
        service = FSMService()
        ctx = SessionContext(completed_modes=frozenset({Mode.EXAMPLE}))

        result = service.handle(FSMState.EXAMPLE_DONE, Continue(), ctx)

        assert result.new_state is FSMState.PRACTICE
        assert result.new_ctx is ctx
        assert result.effects == (PersistSession(),)

    def test_does_not_modify_completed_modes(self) -> None:
        """Continue — это переход, а не завершение режима. Mode.PRACTICE
        будет проставлен позже, в обработчике практики.
        """
        service = FSMService()
        ctx = SessionContext(
            completed_modes=frozenset({Mode.TRAINING, Mode.EXAMPLE}),
        )

        result = service.handle(FSMState.EXAMPLE_DONE, Continue(), ctx)

        assert result.new_ctx.completed_modes == frozenset({Mode.TRAINING, Mode.EXAMPLE})


# ----------------------------------------------------------------------
# Полный happy-path EXAMPLE-блока
# ----------------------------------------------------------------------


class TestExampleHappyPath:
    """E2E: от завершения TRAINING до PRACTICE через EXAMPLE.

    Покрывает стык Коммитов 1 и 2.
    """

    def test_training_then_example_then_practice(self) -> None:
        service = FSMService()
        state = FSMState.TRAINING
        ctx = SessionContext()

        # Теория
        result = service.handle(state, TheoryDone(), ctx)
        state, ctx = result.new_state, result.new_ctx

        # Три правильных ответа подряд
        for _ in range(TRAINING_QUIZ_QUESTIONS):
            result = service.handle(state, SubmitQuizAnswer(correct=True), ctx)
            state, ctx = result.new_state, result.new_ctx
        assert state is FSMState.TRAINING_DONE
        assert Mode.TRAINING in ctx.completed_modes

        # Continue -> EXAMPLE
        result = service.handle(state, Continue(), ctx)
        state, ctx = result.new_state, result.new_ctx
        assert state is FSMState.EXAMPLE

        # Сценарий проигран -> EXAMPLE_DONE
        result = service.handle(state, ScenarioDone(), ctx)
        state, ctx = result.new_state, result.new_ctx
        assert state is FSMState.EXAMPLE_DONE
        assert Mode.EXAMPLE in ctx.completed_modes
        assert Mode.TRAINING in ctx.completed_modes

        # Continue -> PRACTICE
        result = service.handle(state, Continue(), ctx)
        state, ctx = result.new_state, result.new_ctx
        assert state is FSMState.PRACTICE

    def test_direct_to_example_path(self) -> None:
        """Сценарий: пользователь принял предупреждение SKIP_WARNING_1
        и попал в EXAMPLE без прохождения TRAINING. После EXAMPLE
        всё равно идёт в PRACTICE.
        """
        service = FSMService()
        state = FSMState.EXAMPLE
        ctx = SessionContext(completed_modes=frozenset())

        result = service.handle(state, ScenarioDone(), ctx)
        state, ctx = result.new_state, result.new_ctx
        assert state is FSMState.EXAMPLE_DONE
        assert ctx.completed_modes == frozenset({Mode.EXAMPLE})

        result = service.handle(state, Continue(), ctx)
        state, ctx = result.new_state, result.new_ctx
        assert state is FSMState.PRACTICE
