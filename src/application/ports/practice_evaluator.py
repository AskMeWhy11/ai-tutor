"""Порт LLM-оценки диалога режима PRACTICE по чек-листу."""

from __future__ import annotations

from typing import Protocol

from domain.types import ChatMessage, Zone

__all__ = ["PracticeEvaluator"]


class PracticeEvaluator(Protocol):
    """Оценка диалога практики.

    Возвращает кортеж западающих зон (пустой кортеж = всё ок).
    Порядок зон в ответе — канонический ZONE_ORDER, дубликаты исключены.

    case_id — идентификатор учебного кейса (для выбора чек-листа);
    None ⇒ дефолтный кейс.
    """

    async def evaluate(
        self,
        history: tuple[ChatMessage, ...],
        *,
        case_id: str | None = None,
    ) -> tuple[Zone, ...]: ...
