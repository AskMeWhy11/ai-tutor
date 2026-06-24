"""Тесты для ``domain.states``."""

from __future__ import annotations

import pytest

from domain.states import FSMState


@pytest.mark.unit
class TestFSMState:
    """Базовые свойства перечисления FSMState."""

    def test_all_values_are_strings(self) -> None:
        """Каждое значение FSMState — строка (StrEnum)."""
        for state in FSMState:
            assert isinstance(state.value, str)
            assert state.value == state.value.upper()

    def test_str_returns_value(self) -> None:
        """str(state) возвращает значение, а не 'FSMState.XXX'."""
        assert str(FSMState.INIT) == "INIT"
        assert str(FSMState.FINISH) == "FINISH"

    def test_lookup_by_string(self) -> None:
        """FSMState('VALUE') восстанавливает член перечисления."""
        assert FSMState("TRAINING") is FSMState.TRAINING
        assert FSMState("KNOWLEDGE_DONE") is FSMState.KNOWLEDGE_DONE

    def test_invalid_value_raises(self) -> None:
        """Неизвестная строка вызывает ValueError."""
        with pytest.raises(ValueError):
            FSMState("NONEXISTENT_STATE")

    def test_expected_states_present(self) -> None:
        """Все состояния диаграммы присутствуют в перечислении."""
        expected = {
            # Инфраструктурные
            "INIT",
            "RESUME_PROMPT",
            "MENU",
            "WELCOME",
            # Training
            "TRAINING",
            "TRAINING_QUIZ",
            "TRAINING_EXPLAIN",
            "TRAINING_DONE",
            # Предупреждения
            "SKIP_WARNING_1",
            "SKIP_WARNING_2",
            # Practice cycle
            "EXAMPLE",
            "EXAMPLE_DONE",
            "PRACTICE",
            "PRACTICE_EVAL",
            "PRACTICE_PARTIAL",
            "PRACTICE_SUCCESS",
            "KNOWLEDGE",
            "KNOWLEDGE_DONE",
            # Финал
            "FINISH",
        }
        actual = {s.value for s in FSMState}
        assert expected == actual, (
            f"Расхождение состояний.\n"
            f"Лишние: {actual - expected}\n"
            f"Отсутствуют: {expected - actual}"
        )

    def test_total_count(self) -> None:
        """Количество состояний соответствует диаграмме."""
        assert len(FSMState) == 19
