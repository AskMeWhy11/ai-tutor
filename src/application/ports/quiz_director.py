"""Порт LLM-режиссёра TRAINING_QUIZ.

QuizDirector — единая точка для интерактивного квиза:
- генерирует вопросы по фактологии,
- проверяет ответы сотрудника,
- даёт разъяснения при ошибках,
- сам решает, когда квиз пройден (по правилам в промпте из админки).

SessionRunner вызывает `next_turn` в двух случаях:
1. Сотрудник вошёл в TRAINING_QUIZ — `user_text=None` → возвращается первый вопрос.
2. Сотрудник прислал UserMessage — `user_text=<ответ>` → возвращается вердикт + следующий ход.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from domain.context import SessionContext

__all__ = ["QuizDirector", "QuizTurn"]


QuizVerdict = Literal["correct", "incorrect", "none"]
"""Вердикт LLM по последнему ответу.

* "correct"   — ответ верный.
* "incorrect" — ответ неверный.
* "none"      — вердикт не применим (например, это самый первый ход без ответа).
"""


@dataclass(frozen=True, slots=True)
class QuizTurn:
    """Результат одного шага квиза.

    verdict:
        Оценка ответа сотрудника на ПРЕДЫДУЩИЙ вопрос.
    explanation:
        Разъяснение к неверному ответу (показывается в TRAINING_EXPLAIN).
        Может быть пустой строкой, если verdict != "incorrect".
    next_question:
        Текст следующего вопроса. Пустая строка, если квиз завершён.
    done:
        True — квиз успешно пройден, FSM должна перейти в TRAINING_DONE.
        Когда done=True, next_question обычно пустой.
    """

    verdict: QuizVerdict
    explanation: str
    next_question: str
    done: bool


class QuizDirector(Protocol):
    async def next_turn(
        self,
        ctx: SessionContext,
        user_text: str | None,
    ) -> QuizTurn: ...
