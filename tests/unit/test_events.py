"""Тесты для ``domain.events``."""

from __future__ import annotations

import pytest

from domain.events import FSMEvent


@pytest.mark.unit
class TestFSMEvent:
    """Базовые свойства перечисления FSMEvent."""

    def test_all_values_are_strings(self) -> None:
        """Каждое значение FSMEvent — строка (StrEnum)."""
        for event in FSMEvent:
            assert isinstance(event.value, str)
            assert event.value == event.value.upper()

    def test_str_returns_value(self) -> None:
        """str(event) возвращает значение без имени класса."""
        assert str(FSMEvent.CONTINUE) == "CONTINUE"
        assert str(FSMEvent.ALL_CORRECT) == "ALL_CORRECT"

    def test_lookup_by_string(self) -> None:
        """FSMEvent('VALUE') восстанавливает член перечисления."""
        assert FSMEvent("DIALOG_DONE") is FSMEvent.DIALOG_DONE
        assert FSMEvent("REPEAT_CYCLE") is FSMEvent.REPEAT_CYCLE

    def test_invalid_value_raises(self) -> None:
        """Неизвестная строка вызывает ValueError."""
        with pytest.raises(ValueError):
            FSMEvent("NONEXISTENT_EVENT")

    def test_expected_events_present(self) -> None:
        """Все события диаграммы присутствуют в перечислении."""
        expected = {
            # INIT
            "SESSION_FOUND",
            "SESSION_NOT_FOUND",
            "SESSION_EXPIRED",
            # RESUME_PROMPT
            "RESUME_CONFIRMED",
            "RESTART_CONFIRMED",
            # MENU
            "TRAINING_STARTED",
            # WELCOME
            "MODE_TRAINING",
            "MODE_EXAMPLE",
            "MODE_PRACTICE",
            "MODE_EXAMPLE_DIRECT",
            "MODE_PRACTICE_DIRECT",
            "MODE_KNOWLEDGE",
            # SKIP_WARNING
            "WARNING_ACCEPTED",
            "WARNING_DECLINED",
            # TRAINING
            "THEORY_DONE",
            # TRAINING_QUIZ
            "ALL_CORRECT",
            "HAS_ERRORS",
            "MAX_ATTEMPTS",
            # TRAINING_EXPLAIN
            "EXPLANATION_DONE",
            # Универсальный
            "CONTINUE",
            # EXAMPLE / PRACTICE
            "SCENARIO_DONE",
            "DIALOG_DONE",
            # PRACTICE_EVAL
            "ALL_ZONES_OK",
            "HAS_FAILURES",
            # PRACTICE_PARTIAL
            "WEAK_ZONES_SENT",
            # KNOWLEDGE
            "ZONES_DONE",
            "REPEAT_CYCLE",
        }
        actual = {e.value for e in FSMEvent}
        assert expected == actual, (
            f"Расхождение событий.\n"
            f"Лишние: {actual - expected}\n"
            f"Отсутствуют: {expected - actual}"
        )

    def test_total_count(self) -> None:
        """Количество событий соответствует диаграмме."""
        assert len(FSMEvent) == 27
