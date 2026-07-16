"""GigaChat-реализация QuizDirector.

LLM получает:
- системный промпт квиза (редактируется в админке),
- фактологию из контента,
- историю квиза (ctx.quiz_question_index, last_answer_correct),
- последний ответ сотрудника.

Возвращает строгий JSON:
{
  "verdict": "correct" | "incorrect" | "none",
  "explanation": "<пусто или разъяснение>",
  "next_question": "<следующий вопрос или пусто>",
  "done": true | false
}

Promпт должен сам контролировать критерий завершения (например, «3 правильных
ответа всего»). FSM закроет квиз через ctx.quiz_target_questions, как только
LLM вернёт done=true.

Fallback — StubQuizDirector.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

from application.ports.quiz_director import QuizDirector, QuizTurn
from domain.context import SessionContext
from infrastructure.content.case_loader import load_case, resolve_case_id
from infrastructure.content.cc_novichok import TRAINING_BLOCKS
from infrastructure.llm.prompt_store import PromptStore

if TYPE_CHECKING:
    from gigachat import GigaChat

logger = logging.getLogger(__name__)

__all__ = ["GigaChatQuizDirector"]

# Сколько последних реплик квиза передавать модели (вопросы + ответы).
_MAX_HISTORY_MSGS = 24


_USER_TEMPLATE = """\
Сотрудник: {employee}
Цикл практики: {cycle}
Уже задано вопросов: {asked}
Правильных ответов всего: {correct_count}

Выше — весь ход квиза (твои вопросы и ответы сотрудника). Оцени ПОСЛЕДНИЙ
ответ сотрудника именно на ПОСЛЕДНИЙ заданный тобой вопрос — не путай
вопросы между собой и не придумывай новых требований к ответу.

Последний ответ сотрудника:
---
{user_text}
---

Верни СТРОГО JSON в формате:
{{"verdict": "correct"|"incorrect"|"none",
  "explanation": "<разъяснение, если verdict=incorrect; иначе пусто>",
  "next_question": "<следующий вопрос или пусто, если done=true>",
  "done": true|false}}
Без markdown-обёртки, без комментариев."""


_KICKOFF_TEMPLATE = """\
Сотрудник: {employee}
Цикл практики: {cycle}

Это начало квиза — сотрудник только что закончил теорию.
Сформулируй ПЕРВЫЙ проверочный вопрос по фактологии.


Верни СТРОГО JSON:
{{"verdict": "none", "explanation": "", "next_question": "<вопрос>", "done": false}}
Без markdown-обёртки."""


def _build_factology(case_id: str | None = None) -> str:
    """Фактология кейса для контекста LLM-квиза.

    Берём facts.md кейса; если пусто (нет файлов) — fallback на TRAINING_BLOCKS.
    """
    cid = resolve_case_id(case_id)
    facts = load_case(cid).facts.strip()
    if facts:
        return facts
    lines: list[str] = []
    for i, block in enumerate(TRAINING_BLOCKS, start=1):
        lines.append(f"{i}. {block.text}")
    return "\n\n".join(lines)


class GigaChatQuizDirector(QuizDirector):
    def __init__(
        self,
        client: GigaChat,
        prompt_store: PromptStore,
        fallback: QuizDirector,
        model: str | None = None,
    ) -> None:
        self._client = client
        self._prompts = prompt_store
        self._fallback = fallback
        self._model = model

    async def next_turn(
        self,
        ctx: SessionContext,
        user_text: str | None,
    ) -> QuizTurn:
        system_prompt = self._prompts.get_quiz_prompt(ctx.product_id).strip()
        if not system_prompt:
            logger.info("quiz_prompt пуст — fallback на StubQuizDirector")
            return await self._fallback.next_turn(ctx, user_text)

        correct_count = self._count_correct(ctx)

        if user_text is None or not user_text.strip():
            user_msg = _KICKOFF_TEMPLATE.format(
                employee=ctx.employee_name or "сотрудник",
                cycle=ctx.cycle_count,
            )
        else:
            user_msg = _USER_TEMPLATE.format(
                employee=ctx.employee_name or "сотрудник",
                cycle=ctx.cycle_count,
                asked=ctx.quiz_question_index + 1,
                correct_count=correct_count,
                user_text=user_text.strip(),
            )

        # История квиза (вопросы аватара + ответы сотрудника) передаётся
        # как реальные реплики — иначе модель оценивает ответ вслепую,
        # путается и галлюцинирует.
        messages: list[tuple[str, str]] = [("system", system_prompt)]
        for m in ctx.quiz_history[-_MAX_HISTORY_MSGS:]:
            role = "assistant" if m.role == "assistant" else "user"
            messages.append((role, m.text))
        messages.append(("user", user_msg))

        try:
            raw = await self._chat(messages)
        except Exception:
            logger.exception("LLM quiz director failed, fallback")
            return await self._fallback.next_turn(ctx, user_text)

        parsed = _extract_json(raw)
        if parsed is None:
            logger.warning("quiz director: unparseable response %r → fallback", raw)
            return await self._fallback.next_turn(ctx, user_text)

        verdict_raw = str(parsed.get("verdict") or "none").lower()
        if verdict_raw not in ("correct", "incorrect", "none"):
            verdict_raw = "none"

        return QuizTurn(
            verdict=verdict_raw,  # type: ignore[arg-type]
            explanation=str(parsed.get("explanation") or "").strip(),
            next_question=str(parsed.get("next_question") or "").strip(),
            done=bool(parsed.get("done", False)),
        )

    @staticmethod
    def _count_correct(ctx: SessionContext) -> int:
        """Грубая оценка количества правильных ответов до текущего хода.

        FSM не хранит явный счётчик «всего правильных», но при каждом верном
        ответе инкрементирует quiz_question_index. При неверном — индекс
        не растёт, идёт ремедиация. Поэтому quiz_question_index ≈ число
        правильных ответов в текущем прогоне.
        """
        return ctx.quiz_question_index

    async def _chat(self, messages: list[tuple[str, str]]) -> str:
        from typing import Any

        from gigachat.models import Chat, Messages, MessagesRole

        def _role(name: str) -> Any:
            # MessagesRole в разных версиях SDK имеет разный набор констант.
            # Если ASSISTANT отсутствует — отдаём строку, SDK её принимает.
            attr = getattr(MessagesRole, name.upper(), None)
            return attr if attr is not None else name.lower()

        payload = Chat(
            messages=[Messages(role=_role(role), content=content) for role, content in messages],
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
