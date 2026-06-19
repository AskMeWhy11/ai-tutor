"""Порт LLM-оценки диалога режима PRACTICE по чек-листу."""

from __future__ import annotations

from typing import Protocol

from domain.types import ChatMessage, Zone

__all__ = ["PracticeEvaluator"]


class PracticeEvaluator(Protocol):
    """Оценка диалога практики.

    Возвращает кортеж западающих зон (пустой кортеж = всё ок).
    Порядок зон в ответе — канонический ZONE_ORDER, дубликаты исключены.
    """

    async def evaluate(
        self,
        history: tuple[ChatMessage, ...],
    ) -> tuple[Zone, ...]: ...
