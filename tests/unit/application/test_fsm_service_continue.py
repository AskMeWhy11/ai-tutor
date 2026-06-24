"""FSMService: негативные кейсы команды Continue.

Continue — мультистейтовая команда, валидная только в трёх состояниях:
TRAINING_DONE, EXAMPLE_DONE, PRACTICE_SUCCESS. Каждый из этих позитивных
переходов покрыт в соответствующем модульном файле:

* TRAINING_DONE -> EXAMPLE  — test_fsm_service_training.py
* EXAMPLE_DONE  -> PRACTICE — test_fsm_service_example.py
* PRACTICE_SUCCESS -> FINISH — test_fsm_service_knowledge.py

Этот файл фиксирует противоположный инвариант: во ВСЕХ остальных
состояниях Continue должна падать с ValueError. Покрываем состояния,
где регрессия вероятнее всего:

* TRAINING_QUIZ, TRAINING_EXPLAIN — активные циклы внутри блока.
* PRACTICE_PARTIAL — соседнее с PRACTICE_SUCCESS (визуально похоже).
* KNOWLEDGE_DONE — completion-подобное состояние (но валидна RepeatCycle, не Continue).
* FINISH — терминал.

Состояние WELCOME уже покрыто в test_fsm_service_training.py
(TestContinueFromTrainingDone.test_continue_invalid_state) и здесь
не дублируется.

Связанные документы:
    docs/FSM_INVARIANTS.md — таблица команд по состояниям
"""

from __future__ import annotations

import pytest

from application.commands import Continue
from application.fsm_service import FSMService
from domain.context import SessionContext
from domain.states import FSMState

# ----------------------------------------------------------------------
# Continue — невалидные состояния
# ----------------------------------------------------------------------


class TestContinueInvalidStates:
    """Continue недопустима за пределами TRAINING_DONE / EXAMPLE_DONE / PRACTICE_SUCCESS."""

    @pytest.mark.parametrize(
        "state",
        [
            FSMState.TRAINING_QUIZ,
            FSMState.TRAINING_EXPLAIN,
            FSMState.PRACTICE_PARTIAL,
            FSMState.KNOWLEDGE_DONE,
            FSMState.FINISH,
        ],
    )
    def test_continue_raises_in_non_completion_state(
        self,
        state: FSMState,
    ) -> None:
        service = FSMService()
        ctx = SessionContext()

        with pytest.raises(ValueError, match="Continue допустима только"):
            service.handle(state, Continue(), ctx)
