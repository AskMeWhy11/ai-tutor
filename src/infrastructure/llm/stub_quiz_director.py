"""Stub-реализация QuizDirector — детерминированный фолбэк.

Используется когда GigaChat недоступен. Логика проста:
- идём по TRAINING_BLOCKS последовательно,
- проверяем по keywords (как старый StubAnswerChecker),
- засчитываем ответ → следующий вопрос; неверный → разъяснение → тот же вопрос,
- done=True после прохождения всех блоков.
"""

from __future__ import annotations

from application.ports.quiz_director import QuizDirector, QuizTurn
from domain.context import SessionContext
from infrastructure.content.cc_novichok import TRAINING_BLOCKS

__all__ = ["StubQuizDirector"]


class StubQuizDirector(QuizDirector):
    async def next_turn(
        self,
        ctx: SessionContext,
        user_text: str | None,
    ) -> QuizTurn:
        idx = ctx.quiz_question_index
        if idx >= len(TRAINING_BLOCKS):
            # Все блоки уже пройдены.
            return QuizTurn(verdict="none", explanation="", next_question="", done=True)

        # Первый ход — отдаём первый вопрос, без вердикта.
        if user_text is None or not user_text.strip():
            return QuizTurn(
                verdict="none",
                explanation="",
                next_question=TRAINING_BLOCKS[idx].question,
                done=False,
            )

        block = TRAINING_BLOCKS[idx]
        text = user_text.strip().lower()
        correct = bool(block.keywords) and any(kw.lower() in text for kw in block.keywords)

        if not correct:
            return QuizTurn(
                verdict="incorrect",
                explanation=(f"Не совсем так. Правильный ответ: {block.correct_answer}"),
                next_question=block.question,  # тот же вопрос — повторим после разъяснения
                done=False,
            )

        next_idx = idx + 1
        if next_idx >= len(TRAINING_BLOCKS):
            return QuizTurn(verdict="correct", explanation="", next_question="", done=True)

        return QuizTurn(
            verdict="correct",
            explanation="",
            next_question=TRAINING_BLOCKS[next_idx].question,
            done=False,
        )
