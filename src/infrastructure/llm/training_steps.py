"""Этапы TRAINING-flow (эталон: WELCOME → LEARNING → LEARNING_CHECK).

FSM-состояния TRAINING_QUIZ/TRAINING_EXPLAIN — технические узлы этапа
LEARNING_CHECK: единый TRAINING-диалог, промпт Mode.TRAINING, переключение
через плейсхолдер {STEP}.
"""

from __future__ import annotations

from typing import Final

from domain.context import SessionContext
from domain.states import FSMState

__all__ = ["LEARNING_CHECK_STATES", "training_step"]

LEARNING_CHECK_STATES: Final[frozenset[FSMState]] = frozenset(
    {FSMState.TRAINING_QUIZ, FSMState.TRAINING_EXPLAIN}
)


def training_step(state: FSMState, ctx: SessionContext) -> str:
    """Текущий этап TRAINING-flow для {STEP}."""
    if state in LEARNING_CHECK_STATES:
        return "LEARNING_CHECK"
    if state is FSMState.TRAINING and not any(m.role == "user" for m in ctx.dialog_history):
        return "WELCOME"
    return "LEARNING"
