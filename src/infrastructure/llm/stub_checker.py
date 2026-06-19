"""Stub-проверка ответов пользователя по ключевым словам.

Реализует порт `AnswerChecker` (через duck typing — Protocol).
Метод `evaluate_practice` оставлен для обратной совместимости с тестами,
но в новой архитектуре оценкой практики занимается `PracticeEvaluator`.
"""

from __future__ import annotations

from application.ports.answer_checker import CheckResult
from domain.types import Zone
from infrastructure.content.cc_novichok import PRACTICE_SCENARIO, TRAINING_BLOCKS


class StubAnswerChecker:
    """Детерминированный чекер. Заменяется на LLM-чекер позже."""

    async def check_training_answer(
        self,
        block_index: int,
        user_text: str,
    ) -> CheckResult:
        if not 0 <= block_index < len(TRAINING_BLOCKS):
            return CheckResult(correct=False, rationale="block_index out of range")
        keywords = TRAINING_BLOCKS[block_index].keywords
        ok = self._has_any_keyword(user_text, keywords)
        return CheckResult(correct=ok, rationale="keyword-match" if ok else "no-keyword")

    def evaluate_practice(self, zone: Zone, user_text: str) -> bool:
        """Устаревший метод. Используется тестами и старым кодом UI."""
        step = PRACTICE_SCENARIO.get(zone)
        if step is None:
            return False
        return self._has_any_keyword(user_text, step.keywords)

    @staticmethod
    def _has_any_keyword(text: str, keywords: tuple[str, ...]) -> bool:
        if not text or not keywords:
            return False
        normalized = text.lower()
        return any(kw.lower() in normalized for kw in keywords)
