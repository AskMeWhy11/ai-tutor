"""GigaChat-реализация PracticeEvaluator.

LLM получает чек-лист по 3 зонам и историю диалога, возвращает JSON со
списком невыполненных зон. Fallback — stub-оценщик по keywords.

Чек-лист берётся из контента кейса (load_case(case_id).checklist); если
у кейса нет чек-листа — статический CHECKLIST из cc_novichok.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

from application.ports.practice_evaluator import PracticeEvaluator
from domain.types import ZONE_ORDER, ChatMessage, Zone
from infrastructure.content.case_loader import load_case, resolve_case_id
from infrastructure.content.checklists.cc_novichok import CHECKLIST, zone_label

if TYPE_CHECKING:
    from gigachat import GigaChat

logger = logging.getLogger(__name__)

__all__ = ["GigaChatPracticeEvaluator"]


_SYSTEM_PROMPT = """\
Ты — AI-аналитик качества продаж. Сотрудник банка только что провёл
учебный диалог с клиентом (ты видишь полную историю). Тебе нужно оценить,
какие из трёх зон чек-листа сотрудник НЕ отработал.

Зоны и пункты чек-листа:
{checklist_block}

Правила оценки:
1. Зона считается отработанной, если выполнен ХОТЯ БЫ ОДИН ключевой пункт
   из неё. Не требуй идеала.
2. Если сотрудник не сказал по зоне ничего по существу — она западает.
3. Допустимы краткие формулировки. Не штрафуй за стиль.
4. Оценивай ТОЛЬКО реплики сотрудника (роль "сотрудник"), не клиента.

Верни СТРОГО JSON в формате:
{{"weak_zones": ["needs"|"pitch"|"conditions", ...]}}
Пустой массив = всё ок. Без markdown, без комментариев.
"""


class GigaChatPracticeEvaluator(PracticeEvaluator):
    def __init__(
        self,
        client: GigaChat,
        fallback: PracticeEvaluator,
        model: str | None = None,
    ) -> None:
        self._client = client
        self._fallback = fallback
        self._model = model

    async def evaluate(
        self,
        history: tuple[ChatMessage, ...],
        *,
        case_id: str | None = None,
    ) -> tuple[Zone, ...]:
        if not any(m.role == "user" for m in history):
            # Сотрудник не сказал ничего — все зоны западают.
            return ZONE_ORDER

        try:
            raw = await self._chat(
                [
                    ("system", _SYSTEM_PROMPT.format(checklist_block=_format_checklist(case_id))),
                    ("user", _format_history(history)),
                ]
            )
        except Exception:
            logger.exception("LLM evaluator failed, fallback to stub")
            return await self._fallback.evaluate(history, case_id=case_id)

        parsed = _extract_json(raw)
        if parsed is None or "weak_zones" not in parsed:
            logger.warning("LLM evaluator returned unparseable: %r → fallback", raw)
            return await self._fallback.evaluate(history, case_id=case_id)

        raw_zones = parsed.get("weak_zones") or []
        if not isinstance(raw_zones, list):
            return await self._fallback.evaluate(history, case_id=case_id)

        valid: set[str] = set(ZONE_ORDER)
        seen: set[str] = set()
        result: list[Zone] = []
        for z in ZONE_ORDER:  # каноничный порядок
            if z in raw_zones and z in valid and z not in seen:
                seen.add(z)
                result.append(z)
        return tuple(result)

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


def _format_checklist(case_id: str | None) -> str:
    """Чек-лист по зонам из контента кейса; fallback на статический CHECKLIST."""
    cid = resolve_case_id(case_id)
    case_checklist = load_case(cid).checklist

    lines: list[str] = []
    for zone in ZONE_ORDER:
        lines.append(f"\n[{zone}] — {zone_label(zone)}:")
        dto_items = case_checklist.get(zone, ())
        if dto_items:
            for dto in dto_items:
                lines.append(f"  • {dto.id}: {dto.name} — {dto.criteria}")
        else:
            for item in CHECKLIST.get(zone, ()):
                lines.append(f"  • {item.id}: {item.name} — {item.criteria}")
    return "\n".join(lines)


def _format_history(history: tuple[ChatMessage, ...]) -> str:
    lines: list[str] = ["Диалог:"]
    for m in history:
        role = "сотрудник" if m.role == "user" else "клиент"
        lines.append(f"{role}: {m.text}")
    lines.append("\nВерни только JSON.")
    return "\n".join(lines)


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
