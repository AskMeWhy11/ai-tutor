"""Корневой conftest для всех тестов.

Поставляет общие фабрики: SessionContext, ... .
Фикстуры здесь автоматически доступны во всех тестах под tests/.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from domain.context import SessionContext


@pytest.fixture
def make_context() -> Callable[..., SessionContext]:
    """Фабрика SessionContext с переопределяемыми полями.

    Examples:
        >>> ctx = make_context(quiz_question_index=2)
        >>> ctx.quiz_question_index
        2
    """

    def _factory(**overrides: Any) -> SessionContext:
        return SessionContext(**overrides)

    return _factory
