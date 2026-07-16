"""Stub-реализация QuizDirector — детерминированный фолбэк.

Используется когда GigaChat недоступен или вернул невалидный ответ. Логика:
- идём по блокам квиза последовательно,
- проверяем по keywords (как старый StubAnswerChecker),
- засчитываем ответ → следующий вопрос; неверный → разъяснение → тот же вопрос,
- done=True после прохождения всех блоков.

ВАЖНО: блоки берутся ДЛЯ КОНКРЕТНОГО продукта (ctx.product_id). Для
cc_novichok — кураторские TRAINING_BLOCKS. Для остальных кейсов (техники
продаж) — генерируются из чек-листа этого кейса, иначе фолбэк подмешивал
бы факты кредитной карты (ФИКС/«120 дней») в квиз по другой технике.
"""

from __future__ import annotations

from dataclasses import dataclass

from application.ports.quiz_director import QuizDirector, QuizTurn
from domain.context import SessionContext
from domain.types import ZONE_ORDER
from infrastructure.content.case_loader import load_case, resolve_case_id
from infrastructure.content.cc_novichok import TRAINING_BLOCKS
from infrastructure.content.registry import DEFAULT_CASE_ID

__all__ = ["StubQuizDirector"]


@dataclass(frozen=True, slots=True)
class _QuizBlock:
    question: str
    correct_answer: str
    keywords: tuple[str, ...]


def _blocks_for_case(case_id: str | None) -> tuple[_QuizBlock, ...]:
    """Блоки квиза для продукта. cc_novichok — кураторские; иначе из чек-листа."""
    cid = resolve_case_id(case_id)
    if cid == DEFAULT_CASE_ID:
        return tuple(
            _QuizBlock(question=b.question, correct_answer=b.correct_answer, keywords=b.keywords)
            for b in TRAINING_BLOCKS
        )

    checklist = load_case(cid).checklist
    blocks: list[_QuizBlock] = []
    for zone in ZONE_ORDER:
        for item in checklist.get(zone, ()):
            if not item.keywords:
                # Без keywords ответ не проверить — пропускаем такой пункт.
                continue
            # Показываем сотруднику пример фразы, а не сырой criteria
            # (в нём внутренние пометки оценивания вида «— 1»).
            answer = item.example_phrases[0] if item.example_phrases else item.name
            blocks.append(
                _QuizBlock(
                    question=f"Что нужно сделать на шаге «{item.name}»?",
                    correct_answer=answer,
                    keywords=item.keywords,
                )
            )
    return tuple(blocks)


class StubQuizDirector(QuizDirector):
    async def next_turn(
        self,
        ctx: SessionContext,
        user_text: str | None,
    ) -> QuizTurn:
        blocks = _blocks_for_case(ctx.product_id)
        idx = ctx.quiz_question_index
        if not blocks or idx >= len(blocks):
            # Блоков нет или все пройдены.
            return QuizTurn(verdict="none", explanation="", next_question="", done=True)

        # Первый ход — отдаём первый вопрос, без вердикта.
        if user_text is None or not user_text.strip():
            return QuizTurn(
                verdict="none",
                explanation="",
                next_question=blocks[idx].question,
                done=False,
            )

        block = blocks[idx]
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
        if next_idx >= len(blocks):
            return QuizTurn(verdict="correct", explanation="", next_question="", done=True)

        return QuizTurn(
            verdict="correct",
            explanation="",
            next_question=blocks[next_idx].question,
            done=False,
        )
