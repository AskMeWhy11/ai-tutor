"""Эффекты — описания побочных действий, которые применяет внешний слой."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "ClearSession",
    "Effect",
    "EmitHint",
    "EmitMessage",
    "EmitText",
    "PersistSession",
    "PlayAudio",
]


class Effect:
    """Маркерный базовый класс эффектов."""


@dataclass(frozen=True, slots=True)
class PersistSession(Effect):
    """Сохранить (state, ctx) в SessionStore."""


@dataclass(frozen=True, slots=True)
class ClearSession(Effect):
    """Удалить сохранённую сессию (forget / restart)."""


@dataclass(frozen=True, slots=True)
class EmitText(Effect):
    """Отправить реплику аватара в UI как текст."""

    text: str


@dataclass(frozen=True, slots=True)
class EmitHint(Effect):
    """Подсказка-обоснование к предыдущей реплике (режим EXAMPLE)."""

    text: str


@dataclass(frozen=True, slots=True)
class EmitMessage(Effect):
    """Системное сообщение по ключу (i18n-friendly)."""

    key: str


@dataclass(frozen=True, slots=True)
class PlayAudio(Effect):
    """Воспроизвести аудио по URL (озвучка реплики)."""

    url: str
    mime: str
