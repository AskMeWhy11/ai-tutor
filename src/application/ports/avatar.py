"""Порт LLM-аватара (async)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from domain.context import SessionContext
from domain.states import FSMState

__all__ = ["AvatarClient"]


@runtime_checkable
class AvatarClient(Protocol):
    async def next_message(self, state: FSMState, ctx: SessionContext) -> str:
        """Реплика аватара для текущего состояния."""

    async def next_hint(self, state: FSMState, ctx: SessionContext) -> str | None:
        """Подсказка-обоснование к последней реплике (только EXAMPLE).

        Возвращает None, если подсказка для состояния не предусмотрена.
        """
