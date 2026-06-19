"""Stub-реализация StageDirector — фолбэк без LLM.

Простая эвристика по числу user-реплик и ключевым словам:
- TRAINING: 4+ user-реплики → training_understood.
- EXAMPLE: 6+ user-реплик → example_refused_3x;
           «оформляйте/согласен/давайте» в последней реплике → example_accepted.
- PRACTICE: 6+ user-реплик → practice_accepted (заглушка, оценщик решит).
- KNOWLEDGE: «понятно/всё ясно/готов» в последней реплике → knowledge_understood;
             8+ user-реплик → knowledge_understood.
"""

from __future__ import annotations

from application.ports.stage_director import StageDecision, StageDirector
from domain.context import SessionContext
from domain.states import FSMState

__all__ = ["StubStageDirector"]


_ACCEPT_TOKENS = ("оформ", "согласен", "согласна", "давайте", "беру", "хочу карт")
_REFUSE_TOKENS = ("не нужн", "не хочу", "отказ", "передум", "не интерес")
_UNDERSTOOD_TOKENS = ("понятно", "всё ясно", "все ясно", "понял", "поняла", "ясно", "готов")


def _count_user(ctx: SessionContext) -> int:
    return sum(1 for m in ctx.dialog_history if m.role == "user")


def _last_user(ctx: SessionContext) -> str:
    for m in reversed(ctx.dialog_history):
        if m.role == "user":
            return m.text.lower()
    return ""


def _has_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(t in text for t in tokens)


class StubStageDirector(StageDirector):
    async def decide(
        self,
        *,
        state: FSMState,
        ctx: SessionContext,
    ) -> StageDecision:
        last = _last_user(ctx)
        turns = _count_user(ctx)

        if state is FSMState.TRAINING:
            if turns >= 4 or _has_any(last, _UNDERSTOOD_TOKENS):
                return StageDecision(True, "training_understood", "stub: turns/understood")
            return StageDecision(False, "continue", "")

        if state is FSMState.EXAMPLE:
            if _has_any(last, _ACCEPT_TOKENS):
                return StageDecision(True, "example_accepted", "stub: accept")
            refuse_count = sum(
                1
                for m in ctx.dialog_history
                if m.role == "user" and _has_any(m.text.lower(), _REFUSE_TOKENS)
            )
            if refuse_count >= 3 or turns >= 6:
                return StageDecision(True, "example_refused_3x", "stub: 3x refuse")
            return StageDecision(False, "continue", "")

        if state is FSMState.PRACTICE:
            if _has_any(last, _ACCEPT_TOKENS):
                return StageDecision(True, "practice_accepted", "stub: accept")
            refuse_count = sum(
                1
                for m in ctx.dialog_history
                if m.role == "user" and _has_any(m.text.lower(), _REFUSE_TOKENS)
            )
            if refuse_count >= 3:
                return StageDecision(True, "practice_refused", "stub: 3x refuse")
            if turns >= 6:
                return StageDecision(True, "practice_accepted", "stub: turns cap")
            return StageDecision(False, "continue", "")

        if state is FSMState.KNOWLEDGE:
            if _has_any(last, _UNDERSTOOD_TOKENS) or turns >= 8:
                return StageDecision(True, "knowledge_understood", "stub: understood/cap")
            return StageDecision(False, "continue", "")

        return StageDecision(False, "continue", "stub: non-stage state")
