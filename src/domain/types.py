"""Общие типы предметной области, не относящиеся к FSM."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

Zone = Literal["needs", "pitch", "conditions"]
"""Зона диалога продажи. Используется в EXAMPLE/PRACTICE/KNOWLEDGE."""

ZONE_ORDER: Final[tuple[Zone, ...]] = ("needs", "pitch", "conditions")
"""Канонический порядок прохождения зон."""


ChatRole = Literal["user", "assistant"]
"""Роль реплики в истории диалога между сотрудником и аватаром."""


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """Одна реплика в истории диалога режима (EXAMPLE/PRACTICE/KNOWLEDGE/TRAINING).

    role:
        "user"      — реплика сотрудника (текст из формы или распознанной речи).
        "assistant" — реплика аватара (LLM или stub).
    """

    role: ChatRole
    text: str
