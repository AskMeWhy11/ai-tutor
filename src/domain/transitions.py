# src/domain/transitions.py
"""Таблица допустимых переходов FSM обучающего тренажёра."""

from __future__ import annotations

from domain.events import FSMEvent
from domain.states import FSMState

TRANSITIONS: dict[tuple[FSMState, FSMEvent], FSMState] = {
    # INIT
    (FSMState.INIT, FSMEvent.SESSION_FOUND): FSMState.RESUME_PROMPT,
    (FSMState.INIT, FSMEvent.SESSION_NOT_FOUND): FSMState.MENU,
    (FSMState.INIT, FSMEvent.SESSION_EXPIRED): FSMState.MENU,
    # RESUME_PROMPT
    (FSMState.RESUME_PROMPT, FSMEvent.RESTART_CONFIRMED): FSMState.MENU,
    # RESUME_CONFIRMED обрабатывается в FSMService напрямую: целевое
    # состояние = ctx.saved_state, динамическое и в таблицу не помещается.
    # MENU
    (FSMState.MENU, FSMEvent.TRAINING_STARTED): FSMState.WELCOME,
    # WELCOME
    (FSMState.WELCOME, FSMEvent.MODE_TRAINING): FSMState.TRAINING,
    (FSMState.WELCOME, FSMEvent.MODE_EXAMPLE): FSMState.SKIP_WARNING_1,
    (FSMState.WELCOME, FSMEvent.MODE_PRACTICE): FSMState.SKIP_WARNING_2,
    (FSMState.WELCOME, FSMEvent.MODE_EXAMPLE_DIRECT): FSMState.EXAMPLE,
    (FSMState.WELCOME, FSMEvent.MODE_PRACTICE_DIRECT): FSMState.PRACTICE,
    (FSMState.WELCOME, FSMEvent.MODE_KNOWLEDGE): FSMState.KNOWLEDGE,
    # SKIP_WARNING_1
    (FSMState.SKIP_WARNING_1, FSMEvent.WARNING_ACCEPTED): FSMState.EXAMPLE,
    (FSMState.SKIP_WARNING_1, FSMEvent.WARNING_DECLINED): FSMState.WELCOME,
    # SKIP_WARNING_2
    (FSMState.SKIP_WARNING_2, FSMEvent.WARNING_ACCEPTED): FSMState.PRACTICE,
    (FSMState.SKIP_WARNING_2, FSMEvent.WARNING_DECLINED): FSMState.WELCOME,
    # TRAINING
    (FSMState.TRAINING, FSMEvent.THEORY_DONE): FSMState.TRAINING_QUIZ,
    # TRAINING_QUIZ
    (FSMState.TRAINING_QUIZ, FSMEvent.ALL_CORRECT): FSMState.TRAINING_DONE,
    (FSMState.TRAINING_QUIZ, FSMEvent.HAS_ERRORS): FSMState.TRAINING_EXPLAIN,
    (FSMState.TRAINING_QUIZ, FSMEvent.MAX_ATTEMPTS): FSMState.TRAINING_DONE,
    # TRAINING_EXPLAIN
    (FSMState.TRAINING_EXPLAIN, FSMEvent.EXPLANATION_DONE): FSMState.TRAINING_QUIZ,
    # TRAINING_DONE
    (FSMState.TRAINING_DONE, FSMEvent.CONTINUE): FSMState.EXAMPLE,
    # EXAMPLE
    (FSMState.EXAMPLE, FSMEvent.SCENARIO_DONE): FSMState.EXAMPLE_DONE,
    # EXAMPLE_DONE
    (FSMState.EXAMPLE_DONE, FSMEvent.CONTINUE): FSMState.PRACTICE,
    # PRACTICE
    (FSMState.PRACTICE, FSMEvent.DIALOG_DONE): FSMState.PRACTICE_EVAL,
    # PRACTICE_EVAL
    (FSMState.PRACTICE_EVAL, FSMEvent.ALL_ZONES_OK): FSMState.PRACTICE_SUCCESS,
    (FSMState.PRACTICE_EVAL, FSMEvent.HAS_FAILURES): FSMState.PRACTICE_PARTIAL,
    # PRACTICE_PARTIAL
    (FSMState.PRACTICE_PARTIAL, FSMEvent.WEAK_ZONES_SENT): FSMState.KNOWLEDGE,
    # KNOWLEDGE
    (FSMState.KNOWLEDGE, FSMEvent.ZONES_DONE): FSMState.KNOWLEDGE_DONE,
    # KNOWLEDGE_DONE
    (FSMState.KNOWLEDGE_DONE, FSMEvent.REPEAT_CYCLE): FSMState.EXAMPLE,
    # PRACTICE_SUCCESS
    (FSMState.PRACTICE_SUCCESS, FSMEvent.CONTINUE): FSMState.FINISH,
}


def get_next_state(state: FSMState, event: FSMEvent) -> FSMState:
    """Вернуть следующее состояние FSM.

    Args:
        state: Текущее состояние FSM.
        event: Произошедшее событие.

    Returns:
        Следующее состояние FSM.

    Raises:
        KeyError: Если переход ``(state, event)`` не определён в таблице.

    Examples:
        >>> get_next_state(FSMState.INIT, FSMEvent.SESSION_NOT_FOUND)
        <FSMState.MENU: 'MENU'>
        >>> get_next_state(FSMState.TRAINING_QUIZ, FSMEvent.HAS_ERRORS)
        <FSMState.TRAINING_EXPLAIN: 'TRAINING_EXPLAIN'>
    """
    key = (state, event)
    if key not in TRANSITIONS:
        raise KeyError(f"Переход не определён: {state!r} + {event!r}")
    return TRANSITIONS[key]
