"""Тесты для domain.transitions."""

from __future__ import annotations

import pytest

from domain.events import FSMEvent
from domain.states import FSMState
from domain.transitions import TRANSITIONS, get_next_state

# События, обрабатываемые FSMService напрямую (не через TRANSITIONS).
# RESUME_CONFIRMED восстанавливает динамическое целевое состояние = ctx.saved_state.
EVENTS_HANDLED_OUTSIDE_TABLE: frozenset[FSMEvent] = frozenset({FSMEvent.RESUME_CONFIRMED})


@pytest.mark.unit
class TestTransitionsTable:
    def test_all_keys_are_tuples_of_state_and_event(self) -> None:
        for state, event in TRANSITIONS:
            assert isinstance(state, FSMState)
            assert isinstance(event, FSMEvent)

    def test_all_values_are_states(self) -> None:
        for value in TRANSITIONS.values():
            assert isinstance(value, FSMState)

    def test_no_duplicate_keys(self) -> None:
        keys = list(TRANSITIONS.keys())
        assert len(keys) == len(set(keys))

    def test_init_has_three_transitions(self) -> None:
        init_keys = [k for k in TRANSITIONS if k[0] is FSMState.INIT]
        assert len(init_keys) == 3

    def test_every_event_is_used(self) -> None:
        """Инвариант полноты: каждое FSMEvent либо в TRANSITIONS,
        либо в EVENTS_HANDLED_OUTSIDE_TABLE.

        Защита от ситуации «добавили событие в enum, но забыли подключить».
        """
        events_in_table = {event for _, event in TRANSITIONS}
        unused = set(FSMEvent) - events_in_table - EVENTS_HANDLED_OUTSIDE_TABLE
        assert not unused, (
            f"События не используются ни в TRANSITIONS, ни как спецслучаи: {unused}. "
            f"Либо добавьте переход, либо явно занесите в EVENTS_HANDLED_OUTSIDE_TABLE."
        )

    def test_finish_is_terminal(self) -> None:
        """Из FINISH нет исходящих переходов."""
        finish_keys = [k for k in TRANSITIONS if k[0] is FSMState.FINISH]
        assert finish_keys == []


@pytest.mark.unit
class TestGetNextState:
    @pytest.mark.parametrize(
        ("state", "event", "expected"),
        [
            # INIT
            (FSMState.INIT, FSMEvent.SESSION_FOUND, FSMState.RESUME_PROMPT),
            (FSMState.INIT, FSMEvent.SESSION_NOT_FOUND, FSMState.MENU),
            (FSMState.INIT, FSMEvent.SESSION_EXPIRED, FSMState.MENU),
            # RESUME_PROMPT
            (FSMState.RESUME_PROMPT, FSMEvent.RESTART_CONFIRMED, FSMState.MENU),
            # MENU
            (FSMState.MENU, FSMEvent.TRAINING_STARTED, FSMState.WELCOME),
            # WELCOME
            (FSMState.WELCOME, FSMEvent.MODE_TRAINING, FSMState.TRAINING),
            (FSMState.WELCOME, FSMEvent.MODE_EXAMPLE, FSMState.SKIP_WARNING_1),
            (FSMState.WELCOME, FSMEvent.MODE_PRACTICE, FSMState.SKIP_WARNING_2),
            (FSMState.WELCOME, FSMEvent.MODE_EXAMPLE_DIRECT, FSMState.EXAMPLE),
            (FSMState.WELCOME, FSMEvent.MODE_PRACTICE_DIRECT, FSMState.PRACTICE),
            (FSMState.WELCOME, FSMEvent.MODE_KNOWLEDGE, FSMState.KNOWLEDGE),
            # SKIP_WARNING_1
            (FSMState.SKIP_WARNING_1, FSMEvent.WARNING_ACCEPTED, FSMState.EXAMPLE),
            (FSMState.SKIP_WARNING_1, FSMEvent.WARNING_DECLINED, FSMState.WELCOME),
            # SKIP_WARNING_2
            (FSMState.SKIP_WARNING_2, FSMEvent.WARNING_ACCEPTED, FSMState.PRACTICE),
            (FSMState.SKIP_WARNING_2, FSMEvent.WARNING_DECLINED, FSMState.WELCOME),
            # TRAINING
            (FSMState.TRAINING, FSMEvent.THEORY_DONE, FSMState.TRAINING_QUIZ),
            # TRAINING_QUIZ
            (FSMState.TRAINING_QUIZ, FSMEvent.ALL_CORRECT, FSMState.TRAINING_DONE),
            (FSMState.TRAINING_QUIZ, FSMEvent.HAS_ERRORS, FSMState.TRAINING_EXPLAIN),
            (FSMState.TRAINING_QUIZ, FSMEvent.MAX_ATTEMPTS, FSMState.TRAINING_DONE),
            # TRAINING_EXPLAIN
            (FSMState.TRAINING_EXPLAIN, FSMEvent.EXPLANATION_DONE, FSMState.TRAINING_QUIZ),
            # TRAINING_DONE
            (FSMState.TRAINING_DONE, FSMEvent.CONTINUE, FSMState.EXAMPLE),
            # EXAMPLE
            (FSMState.EXAMPLE, FSMEvent.SCENARIO_DONE, FSMState.EXAMPLE_DONE),
            # EXAMPLE_DONE
            (FSMState.EXAMPLE_DONE, FSMEvent.CONTINUE, FSMState.PRACTICE),
            # PRACTICE
            (FSMState.PRACTICE, FSMEvent.DIALOG_DONE, FSMState.PRACTICE_EVAL),
            # PRACTICE_EVAL
            (FSMState.PRACTICE_EVAL, FSMEvent.ALL_ZONES_OK, FSMState.PRACTICE_SUCCESS),
            (FSMState.PRACTICE_EVAL, FSMEvent.HAS_FAILURES, FSMState.PRACTICE_PARTIAL),
            # PRACTICE_PARTIAL
            (FSMState.PRACTICE_PARTIAL, FSMEvent.WEAK_ZONES_SENT, FSMState.KNOWLEDGE),
            # KNOWLEDGE
            (FSMState.KNOWLEDGE, FSMEvent.ZONES_DONE, FSMState.KNOWLEDGE_DONE),
            # KNOWLEDGE_DONE
            (FSMState.KNOWLEDGE_DONE, FSMEvent.REPEAT_CYCLE, FSMState.EXAMPLE),
            # PRACTICE_SUCCESS
            (FSMState.PRACTICE_SUCCESS, FSMEvent.CONTINUE, FSMState.FINISH),
        ],
    )
    def test_happy_path(
        self,
        state: FSMState,
        event: FSMEvent,
        expected: FSMState,
    ) -> None:
        assert get_next_state(state, event) is expected

    def test_undefined_transition_raises_key_error(self) -> None:
        with pytest.raises(KeyError):
            get_next_state(FSMState.FINISH, FSMEvent.CONTINUE)

    def test_key_error_message_contains_state(self) -> None:
        with pytest.raises(KeyError, match="FINISH"):
            get_next_state(FSMState.FINISH, FSMEvent.CONTINUE)

    def test_key_error_message_contains_event(self) -> None:
        with pytest.raises(KeyError, match="CONTINUE"):
            get_next_state(FSMState.FINISH, FSMEvent.CONTINUE)

    def test_resume_confirmed_not_in_table(self) -> None:
        """RESUME_CONFIRMED восстанавливает saved_state — не входит в таблицу."""
        with pytest.raises(KeyError):
            get_next_state(FSMState.RESUME_PROMPT, FSMEvent.RESUME_CONFIRMED)
