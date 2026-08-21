"""GigaChat-реализация StageDirector — LLM-судья стадии.

Получает:
- stage_director_prompt (system, из админки),
- название текущего состояния,
- историю диалога (ctx.dialog_history),
- счётчики (turns, refuse_count).

Возвращает строгий JSON:
{
  "done": true|false,
  "outcome": "continue" | "training_understood" |
             "example_accepted" | "example_refused_3x" |
             "practice_accepted" | "practice_refused" |
             "knowledge_understood",
  "reason": "<краткое обоснование>"
}

Fallback — StubStageDirector.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, get_args

from application.ports.stage_director import (
    StageDecision,
    StageDirector,
    StageOutcome,
)
from domain.context import SessionContext
from domain.states import FSMState, Mode
from infrastructure.content.case_loader import resolve_case_id
from infrastructure.content.registry import DEFAULT_CASE_ID
from infrastructure.llm.prompt_store import PromptStore
from infrastructure.llm.training_steps import training_step

if TYPE_CHECKING:
    from gigachat import GigaChat

logger = logging.getLogger(__name__)

__all__ = ["GigaChatStageDirector"]


_VALID_OUTCOMES: frozenset[str] = frozenset(get_args(StageOutcome))

# Допустимые outcome по состоянию.
# FSM-состояние → режим, чей stage_director-промпт используется.
_STATE_TO_MODE: dict[FSMState, Mode] = {
    FSMState.TRAINING: Mode.TRAINING,
    # Этап LEARNING_CHECK — тот же TRAINING-судья (learning-check контур).
    FSMState.TRAINING_QUIZ: Mode.TRAINING,
    FSMState.EXAMPLE: Mode.EXAMPLE,
    FSMState.PRACTICE: Mode.PRACTICE,
    FSMState.KNOWLEDGE: Mode.KNOWLEDGE,
}

_ALLOWED_BY_STATE: dict[FSMState, frozenset[str]] = {
    FSMState.TRAINING: frozenset({"continue", "training_understood"}),
    FSMState.TRAINING_QUIZ: frozenset(
        {
            "continue",  # STEP_STATUS=LEARNING_CHECK_STARTED
            "learning_check_finished_success",
            "learning_check_finished_failed",
        }
    ),
    FSMState.EXAMPLE: frozenset({"continue", "example_accepted", "example_refused_3x"}),
    FSMState.PRACTICE: frozenset({"continue", "practice_accepted", "practice_refused"}),
    FSMState.KNOWLEDGE: frozenset({"continue", "knowledge_understood"}),
}

_ACCEPT_TOKENS = ("оформ", "согласен", "согласна", "давайте", "беру", "хочу карт")
_REFUSE_TOKENS = ("не нужн", "не хочу", "отказ", "передум", "не интерес")

# Минимум содержательных реплик аватара в TRAINING, прежде чем стадию
# вообще можно закрывать (техники продаж). Промпт-правила модель нередко
# игнорирует и уводит в квиз после 2–3 реплик, поэтому держим жёсткий пол:
# сначала учим, потом спрашиваем. cc_novichok не затрагиваем.
_MIN_TRAINING_AVATAR_TURNS = 5


_USER_TEMPLATE = """\
Текущее состояние FSM: {state}
Текущий этап TRAINING-flow (STEP): {step}
Допустимые значения outcome: {allowed}

Счётчики:
- user-реплик в стадии: {turns}
- отказов клиента: {refuse_count}
- цикл практики: {cycle}

ИСТОРИЯ ДИАЛОГА (последние реплики, новейшие внизу):
---
{history}
---

Реши, пора ли завершать стадию. Верни СТРОГО JSON:
{{"done": true|false,
  "outcome": "<одно из допустимых>",
  "reason": "<краткое обоснование 1 фразой>"}}
Без markdown-обёртки, без комментариев."""


def _format_history(ctx: SessionContext, max_msgs: int = 20) -> str:
    msgs = ctx.dialog_history[-max_msgs:]
    if not msgs:
        return "(пусто)"
    lines: list[str] = []
    for m in msgs:
        role = "СОТРУДНИК" if m.role == "user" else "АВАТАР"
        lines.append(f"{role}: {m.text}")
    return "\n".join(lines)


def _count_refuse(ctx: SessionContext) -> int:
    n = 0
    for m in ctx.dialog_history:
        if m.role != "user":
            continue
        low = m.text.lower()
        if any(t in low for t in _REFUSE_TOKENS):
            n += 1
    return n


def _count_user(ctx: SessionContext) -> int:
    return sum(1 for m in ctx.dialog_history if m.role == "user")


def _count_avatar(ctx: SessionContext) -> int:
    return sum(1 for m in ctx.dialog_history if m.role != "user")


def _training_too_early(state: FSMState, ctx: SessionContext) -> bool:
    """TRAINING техники продаж ещё не набрал минимум реплик теории."""
    if state is not FSMState.TRAINING:
        return False
    if resolve_case_id(ctx.product_id) == DEFAULT_CASE_ID:
        return False
    return _count_avatar(ctx) < _MIN_TRAINING_AVATAR_TURNS


class GigaChatStageDirector(StageDirector):
    def __init__(
        self,
        client: GigaChat,
        prompt_store: PromptStore,
        fallback: StageDirector,
        model: str | None = None,
    ) -> None:
        self._client = client
        self._prompts = prompt_store
        self._fallback = fallback
        self._model = model

    async def decide(
        self,
        *,
        state: FSMState,
        ctx: SessionContext,
    ) -> StageDecision:
        allowed = _ALLOWED_BY_STATE.get(state)
        if allowed is None:
            return StageDecision(False, "continue", "non-stage state")

        # Жёсткий пол: не закрываем теорию техники раньше времени —
        # сначала учим, потом спрашиваем. LLM тут не спрашиваем вовсе.
        if _training_too_early(state, ctx):
            logger.info(
                "stage_director: TRAINING рано закрывать (реплик аватара %d < %d) — continue",
                _count_avatar(ctx),
                _MIN_TRAINING_AVATAR_TURNS,
            )
            return StageDecision(False, "continue", "теория ещё не рассказана целиком")

        system_prompt = self._prompts.get_stage_director_prompt(
            _STATE_TO_MODE[state], ctx.product_id
        ).strip()
        if not system_prompt:
            logger.info("stage_director_prompt пуст — fallback на stub")
            return await self._fallback.decide(state=state, ctx=ctx)

        user_msg = _USER_TEMPLATE.format(
            state=state.value,
            step=training_step(state, ctx),
            allowed=", ".join(sorted(allowed)),
            turns=_count_user(ctx),
            refuse_count=_count_refuse(ctx),
            cycle=ctx.cycle_count,
            history=_format_history(ctx),
        )

        try:
            raw = await self._chat(
                [
                    ("system", system_prompt),
                    ("user", user_msg),
                ]
            )
        except Exception:
            logger.exception("LLM stage director failed, fallback")
            return await self._fallback.decide(state=state, ctx=ctx)

        parsed = _extract_json(raw)
        if parsed is None:
            logger.warning("stage director: unparseable response %r → fallback", raw)
            return await self._fallback.decide(state=state, ctx=ctx)

        outcome_raw = str(parsed.get("outcome") or "continue").strip()
        if outcome_raw not in _VALID_OUTCOMES or outcome_raw not in allowed:
            logger.warning(
                "stage director: outcome=%r not allowed in state=%s → continue",
                outcome_raw,
                state,
            )
            outcome_raw = "continue"

        done = bool(parsed.get("done", False))
        if outcome_raw == "continue":
            done = False
        elif outcome_raw != "continue" and not done:
            # outcome != continue, но done=false — нелогично; считаем done=true.
            done = True

        reason = str(parsed.get("reason") or "").strip()
        return StageDecision(done=done, outcome=outcome_raw, reason=reason)  # type: ignore[arg-type]

    async def _chat(self, messages: list[tuple[str, str]]) -> str:
        from gigachat.models import Chat, Messages, MessagesRole

        role_map = {
            "system": MessagesRole.SYSTEM,
            "user": MessagesRole.USER,
        }
        payload = Chat(
            messages=[Messages(role=role_map[role], content=content) for role, content in messages],
        )
        if self._model:
            payload.model = self._model
        resp = await self._client.achat(payload)
        choices = getattr(resp, "choices", None) or []
        if not choices:
            return ""
        message = getattr(choices[0], "message", None)
        return str(getattr(message, "content", "") if message else "").strip()


def _extract_json(raw: str) -> dict[str, object] | None:
    if not raw:
        return None
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        obj = json.loads(match.group(0))
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None
