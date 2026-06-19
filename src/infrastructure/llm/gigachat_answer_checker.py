"""GigaChat-реализация AnswerChecker для TRAINING_QUIZ."""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

from application.ports.answer_checker import AnswerChecker, CheckResult
from infrastructure.content.cc_novichok import TRAINING_BLOCKS

if TYPE_CHECKING:
    from gigachat import GigaChat

logger = logging.getLogger(__name__)

__all__ = ["GigaChatAnswerChecker"]


_SYSTEM_PROMPT = """\
Ты — AI-наставник Сбербанка. Твоя задача — оценить ответ сотрудника на
проверочный вопрос. Сотрудник учится продавать кредитные карты Сбера.

Критерии оценки:
1. Ответ засчитывается, если он по СУТИ соответствует эталонному ответу,
   даже если сформулирован своими словами.
2. Ответ НЕ засчитывается, если упущен ключевой факт или назван неверный
   факт/цифра/продукт.
3. Допустимы краткие, но точные ответы.
4. Регистр и пунктуация не важны.

Верни СТРОГО JSON в формате:
{"correct": true|false, "rationale": "<краткое пояснение, 1 фраза>"}
Без markdown-обёртки, без комментариев.
"""

_USER_TEMPLATE = """\
Вопрос: {question}
Эталонный ответ: {correct_answer}

Ответ сотрудника: {user_text}

Оцени ответ. Верни только JSON."""


class GigaChatAnswerChecker(AnswerChecker):
    def __init__(
        self,
        client: GigaChat,
        fallback: AnswerChecker,
        model: str | None = None,
    ) -> None:
        self._client = client
        self._fallback = fallback
        self._model = model

    async def check_training_answer(
        self,
        block_index: int,
        user_text: str,
    ) -> CheckResult:
        if not 0 <= block_index < len(TRAINING_BLOCKS):
            return CheckResult(correct=False, rationale="block_index out of range")
        block = TRAINING_BLOCKS[block_index]
        text = (user_text or "").strip()
        if not text:
            return CheckResult(correct=False, rationale="пустой ответ")

        try:
            raw = await self._chat(
                [
                    ("system", _SYSTEM_PROMPT),
                    (
                        "user",
                        _USER_TEMPLATE.format(
                            question=block.question,
                            correct_answer=block.correct_answer,
                            user_text=text,
                        ),
                    ),
                ]
            )
        except Exception:
            logger.exception("LLM checker failed, fallback to stub")
            return await self._fallback.check_training_answer(block_index, text)

        parsed = _extract_json(raw)
        if parsed is None or "correct" not in parsed:
            logger.warning("LLM checker returned unparseable: %r → fallback", raw)
            return await self._fallback.check_training_answer(block_index, text)

        return CheckResult(
            correct=bool(parsed.get("correct")),
            rationale=str(parsed.get("rationale", ""))[:200],
        )

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
    """Достать JSON-объект из ответа LLM. Терпит markdown-обёртку и мусор."""
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
