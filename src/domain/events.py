"""События (триггеры) FSM обучающего тренажёра.

Событие — это то, что вызывает переход из одного состояния в другое.
Именование: глагол или факт, описывающий что произошло.

Соответствие событий переходам на диаграмме:

.. code-block:: text

    INIT
      SESSION_FOUND      → RESUME_PROMPT
      SESSION_NOT_FOUND  → MENU
      # SESSION_EXPIRED    → MENU

    RESUME_PROMPT
      RESUME_CONFIRMED   → PrevState
      RESTART_CONFIRMED  → MENU

    MENU
      TRAINING_STARTED   → WELCOME

    WELCOME / ChoiceMode
      MODE_TRAINING      → TRAINING
      MODE_EXAMPLE       → SKIP_WARNING_1
      MODE_PRACTICE      → SKIP_WARNING_2
      MODE_EXAMPLE_DIRECT  → EXAMPLE  (если TRAINING пройден)
      MODE_PRACTICE_DIRECT → PRACTICE (если TRAINING пройден)
      MODE_KNOWLEDGE       → KNOWLEDGE (если KNOWLEDGE разблокирован)

    SKIP_WARNING_1 / SKIP_WARNING_2
      WARNING_ACCEPTED   → EXAMPLE / PRACTICE

    TRAINING
      THEORY_DONE        → TRAINING_QUIZ

    TRAINING_QUIZ
      ALL_CORRECT        → TRAINING_DONE
      HAS_ERRORS         → TRAINING_EXPLAIN
      MAX_ATTEMPTS       → TRAINING_DONE

    TRAINING_EXPLAIN
      EXPLANATION_DONE   → TRAINING_QUIZ

    TRAINING_DONE
      CONTINUE           → EXAMPLE

    EXAMPLE
      SCENARIO_DONE      → EXAMPLE_DONE

    EXAMPLE_DONE
      CONTINUE           → PRACTICE

    PRACTICE
      DIALOG_DONE        → PRACTICE_EVAL

    PRACTICE_EVAL
      ALL_ZONES_OK       → PRACTICE_SUCCESS
      HAS_FAILURES       → PRACTICE_PARTIAL

    PRACTICE_PARTIAL
      WEAK_ZONES_SENT    → KNOWLEDGE

    KNOWLEDGE
      ZONES_DONE         → KNOWLEDGE_DONE

    KNOWLEDGE_DONE
      REPEAT_CYCLE       → EXAMPLE

    PRACTICE_SUCCESS
      CONTINUE           → FINISH
"""

from __future__ import annotations

from enum import StrEnum


class FSMEvent(StrEnum):
    """Полный список событий FSM.

    Examples:
        >>> FSMEvent.SESSION_FOUND
        <FSMEvent.SESSION_FOUND: 'SESSION_FOUND'>
        >>> str(FSMEvent.ALL_CORRECT)
        'ALL_CORRECT'
        >>> FSMEvent("DIALOG_DONE") is FSMEvent.DIALOG_DONE
        True
    """

    # ------------------------------------------------------------------
    # INIT
    # ------------------------------------------------------------------

    SESSION_FOUND = "SESSION_FOUND"
    """Найдена активная сессия возрастом < 48 ч."""

    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    """Сессия не найдена — первый запуск."""

    SESSION_EXPIRED = "SESSION_EXPIRED"
    """Найденная сессия старше 48 часов — считается истёкшей,
    обрабатывается как новый запуск (поведение из roadmap, Срез 2)."""

    # ------------------------------------------------------------------
    # RESUME_PROMPT
    # ------------------------------------------------------------------

    RESUME_CONFIRMED = "RESUME_CONFIRMED"
    """Сотрудник выбрал «Продолжить» прерванную сессию."""

    RESTART_CONFIRMED = "RESTART_CONFIRMED"
    """Сотрудник выбрал «Начать заново»."""

    # ------------------------------------------------------------------
    # MENU
    # ------------------------------------------------------------------

    TRAINING_STARTED = "TRAINING_STARTED"
    """Нажата кнопка «Начать обучение» в меню."""

    # ------------------------------------------------------------------
    # WELCOME / ChoiceMode
    # ------------------------------------------------------------------

    MODE_TRAINING = "MODE_TRAINING"
    """Выбран режим «Обучение»."""

    MODE_EXAMPLE = "MODE_EXAMPLE"
    """Выбран режим «Пример» (без прохождения «Обучения»)."""

    MODE_PRACTICE = "MODE_PRACTICE"
    """Выбран режим «Практика» (без прохождения «Обучения»)."""

    MODE_EXAMPLE_DIRECT = "MODE_EXAMPLE_DIRECT"
    """Выбран режим «Пример» при пройденном «Обучении» — без предупреждения."""

    MODE_PRACTICE_DIRECT = "MODE_PRACTICE_DIRECT"
    """Выбран режим «Практика» при пройденном «Обучении» — без предупреждения."""

    MODE_KNOWLEDGE = "MODE_KNOWLEDGE"
    """Выбран режим «Знания» (доступен только если PRACTICE пройдена и есть западающие зоны)."""

    # ------------------------------------------------------------------
    # SKIP_WARNING
    # ------------------------------------------------------------------

    WARNING_ACCEPTED = "WARNING_ACCEPTED"
    """Сотрудник подтвердил переход несмотря на предупреждение."""

    WARNING_DECLINED = "WARNING_DECLINED"
    """Сотрудник отказался и вернулся к выбору режима."""

    # ------------------------------------------------------------------
    # TRAINING
    # ------------------------------------------------------------------

    THEORY_DONE = "THEORY_DONE"
    """Аватар завершил изложение теории — переход к проверке."""

    # ------------------------------------------------------------------
    # TRAINING_QUIZ
    # ------------------------------------------------------------------

    ALL_CORRECT = "ALL_CORRECT"
    """Все три проверочных вопроса отвечены верно."""

    HAS_ERRORS = "HAS_ERRORS"
    """Хотя бы один ответ неверен — переход к разбору."""

    MAX_ATTEMPTS = "MAX_ATTEMPTS"
    """Исчерпано максимальное число попыток — принудительное завершение."""

    # ------------------------------------------------------------------
    # TRAINING_EXPLAIN / TRAINING_DONE
    # ------------------------------------------------------------------

    EXPLANATION_DONE = "EXPLANATION_DONE"
    """Разбор ошибки завершён — возврат к вопросу."""

    # ------------------------------------------------------------------
    # Универсальный триггер продолжения
    # ------------------------------------------------------------------

    CONTINUE = "CONTINUE"
    """
    Универсальный триггер «Продолжить».

    Используется в состояниях, где единственное действие —
    перейти к следующему шагу:

    * TRAINING_DONE  → EXAMPLE
    * EXAMPLE_DONE   → PRACTICE
    * PRACTICE_SUCCESS → FINISH
    """

    # ------------------------------------------------------------------
    # EXAMPLE / PRACTICE
    # ------------------------------------------------------------------

    SCENARIO_DONE = "SCENARIO_DONE"
    """Сценарий режима «Пример» завершён."""

    DIALOG_DONE = "DIALOG_DONE"
    """Диалог режима «Практика» завершён."""

    # ------------------------------------------------------------------
    # PRACTICE_EVAL
    # ------------------------------------------------------------------

    ALL_ZONES_OK = "ALL_ZONES_OK"
    """Все западающие зоны отработаны корректно."""

    HAS_FAILURES = "HAS_FAILURES"
    """Одна или несколько зон не отработаны."""

    # ------------------------------------------------------------------
    # PRACTICE_PARTIAL → KNOWLEDGE
    # ------------------------------------------------------------------

    WEAK_ZONES_SENT = "WEAK_ZONES_SENT"
    """Список проваленных зон передан в режим «Знания»."""

    # ------------------------------------------------------------------
    # KNOWLEDGE / KNOWLEDGE_DONE
    # ------------------------------------------------------------------

    ZONES_DONE = "ZONES_DONE"
    """Все западающие зоны проработаны в режиме «Знания»."""

    REPEAT_CYCLE = "REPEAT_CYCLE"
    """Запуск нового цикла EXAMPLE → PRACTICE → (KNOWLEDGE)."""
