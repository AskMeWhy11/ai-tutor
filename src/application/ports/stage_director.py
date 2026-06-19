"""Порт LLM-судьи стадии: решает, пора ли завершать TRAINING/EXAMPLE/PRACTICE/KNOWLEDGE.

Все переходы между стадиями (кроме первичного выбора режима в WELCOME)
принимает LLM через StageDirector. SessionRunner вызывает `decide` после
каждой UserMessage в режимных состояниях и при `done=True` авто-эмитит
соответствующую команду FSM.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from domain.context import SessionContext
from domain.states import FSMState

__all__ = ["StageDecision", "StageDirector", "StageOutcome"]


StageOutcome = Literal[
    "continue",
    "training_understood",
    "example_accepted",
    "example_refused_3x",
    "practice_accepted",
    "practice_refused",
    "knowledge_understood",
]


@dataclass(frozen=True, slots=True)
class StageDecision:
    done: bool
    outcome: StageOutcome
    reason: str = ""


class StageDirector(Protocol):
    async def decide(
        self,
        *,
        state: FSMState,
        ctx: SessionContext,
    ) -> StageDecision: ...
