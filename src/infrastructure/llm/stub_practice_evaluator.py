"""Stub-оценщик диалога практики.

Логика:
- Идём по всем user-репликам в истории, агрегируем их в один lowercase-блоб.
- Для каждой зоны проверяем: есть ли хоть одно keyword из чек-листа этой
  зоны в блобе. Если нет — зона западает.
- Возвращаем зоны в каноническом порядке ZONE_ORDER.

case_id игнорируется: stub работает на статическом чек-листе cc_novichok.
"""

from __future__ import annotations

from domain.types import ZONE_ORDER, ChatMessage, Zone
from infrastructure.content.checklists.cc_novichok import keywords_for_zone


class StubPracticeEvaluator:
    async def evaluate(
        self,
        history: tuple[ChatMessage, ...],
        *,
        case_id: str | None = None,
    ) -> tuple[Zone, ...]:
        user_text = " ".join(m.text for m in history if m.role == "user").lower()
        if not user_text.strip():
            # Если сотрудник вообще ничего не сказал — все зоны западают.
            return ZONE_ORDER

        weak: list[Zone] = []
        for zone in ZONE_ORDER:
            kws = keywords_for_zone(zone)
            if not kws:
                # Если в зоне нет keywords — считаем её ок (нечего проверить).
                continue
            if not any(kw in user_text for kw in kws):
                weak.append(zone)
        return tuple(weak)
