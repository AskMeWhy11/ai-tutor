"""Порт LLM-диалога TRAINING_QUIZ."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

__all__ = ["AnswerChecker", "CheckResult"]


@dataclass(frozen=True, slots=True)
class CheckResult:
    """Результат проверки ответа.

    correct: верен ли ответ по сути.
    rationale: короткое пояснение от чекера (для отладки/логов; UI его пока
        не показывает — разъяснение генерирует аватар в TRAINING_EXPLAIN).
    """

    correct: bool
    rationale: str = ""


class AnswerChecker(Protocol):
    """Проверка ответа на проверочный вопрос блока обучения.

    block_index: индекс блока в TRAINING_BLOCKS (он же ctx.quiz_question_index).
    user_text:   реплика сотрудника.
    """

    async def check_training_answer(
        self,
        block_index: int,
        user_text: str,
    ) -> CheckResult: ...
