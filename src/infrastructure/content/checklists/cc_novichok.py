"""Чек-лист продажи КК_Новичок, структурированный по 3 зонам диалога.

Используется:
- LLM-оценщиком практики (пункты по зонам передаются в промпт);
- stub-оценщиком (keywords пунктов агрегируются в keywords зоны);
- админкой (когда появится редактирование контента).
"""

from __future__ import annotations

from dataclasses import dataclass

from domain.types import ZONE_ORDER, Zone

__all__ = ["CHECKLIST", "ChecklistItem", "keywords_for_zone", "zone_label"]


@dataclass(frozen=True, slots=True)
class ChecklistItem:
    """Один пункт чек-листа.

    id: внешний код пункта (для логов/админки).
    name: краткое описание для наставника.
    criteria: критерий оценки (что считается выполнением).
    example_phrases: эталонные формулировки (примеры).
    keywords: ключевые слова для stub-оценщика (lowercase, опционально).
    """

    id: str
    name: str
    criteria: str
    example_phrases: tuple[str, ...]
    keywords: tuple[str, ...] = ()


# 3 зоны x 2-3 пункта. Сжатая версия из example_prompts.md, адаптированная
# под нашу фактологию (ФИКС / 120 дней).
CHECKLIST: dict[Zone, tuple[ChecklistItem, ...]] = {
    "needs": (
        ChecklistItem(
            id="N1",
            name="Уточнил формат: наличные или безнал",
            criteria=(
                "Сотрудник задал уточняющий вопрос до презентации продукта: "
                "наличные нужны клиенту, безнал, перевод или покупки."
            ),
            example_phrases=(
                "Вам удобнее наличными или картой?",
                "Деньги нужны на одну операцию или будут частями?",
                "Куда планируете их потратить — в магазин или снимать?",
            ),
            keywords=("налич", "карт", "перевод", "куда", "на что", "удобнее"),
        ),
        ChecklistItem(
            id="N2",
            name="Не начал с продукта",
            criteria=(
                "Сотрудник НЕ предложил карту в первой реплике, " "до выяснения потребности."
            ),
            example_phrases=("Расскажите, в чём ситуация — я подберу подходящую карту.",),
            keywords=(),
        ),
    ),
    "pitch": (
        ChecklistItem(
            id="P1",
            name="Выбрал карту под потребность",
            criteria=(
                "Под наличные/переводы предложил ФИКС. "
                "Под покупки — СберКарта 120 дней. "
                "Не предложил «120 дней» под наличные."
            ),
            example_phrases=(
                "Тогда вам подойдёт ФИКС — для снятий наличных.",
                "Если оплачивать в магазине, лучше 120 дней — без процентов до 120 дней.",
            ),
            keywords=("фикс", "120 дней", "120дней", "сберкарт"),
        ),
        ChecklistItem(
            id="P2",
            name="Назвал ключевую цифру",
            criteria=(
                "Озвучил конкретный лимит/срок: 50 000 ₽/мес для ФИКС "
                "или 120 дней без процентов для «120 дней»."
            ),
            example_phrases=(
                "До 50 тысяч в месяц снятий бесплатно.",
                "120 дней без процентов на покупки.",
            ),
            keywords=("50", "тыс", "120 дн", "120дн"),
        ),
    ),
    "conditions": (
        ChecklistItem(
            id="C1",
            name="Проговорил условие бесплатности",
            criteria=(
                "Чётко озвучено: для ФИКС — возврат до конца месяца; "
                "для 120 дней — возврат в течение 120 дней."
            ),
            example_phrases=(
                "Если вернёте до конца месяца — без комиссии.",
                "Если вернёте за 120 дней — без процентов.",
            ),
            keywords=("конец месяца", "до конца", "верн", "120 дн"),
        ),
        ChecklistItem(
            id="C2",
            name="Снял возражение по процентам",
            criteria=(
                "Если клиент спросил про проценты — сотрудник пояснил, "
                "что при условии возврата проценты/комиссии не начисляются."
            ),
            example_phrases=(
                "Никаких процентов, если вернёте вовремя.",
                "Льготный период покрывает обычные траты.",
            ),
            keywords=("беспл", "процент", "комисс"),
        ),
    ),
}


_ZONE_LABELS_RU: dict[Zone, str] = {
    "needs": "выявление потребности",
    "pitch": "презентация продукта",
    "conditions": "условия и возражения",
}


def keywords_for_zone(zone: Zone) -> tuple[str, ...]:
    """Объединить keywords всех пунктов зоны для stub-оценщика."""
    seen: set[str] = set()
    result: list[str] = []
    for item in CHECKLIST.get(zone, ()):
        for kw in item.keywords:
            kw_low = kw.lower()
            if kw_low not in seen:
                seen.add(kw_low)
                result.append(kw_low)
    return tuple(result)


def zone_label(zone: Zone) -> str:
    return _ZONE_LABELS_RU.get(zone, zone)


# Порядок экспорта зон совпадает с ZONE_ORDER — чтобы оценщики возвращали
# зоны в каноническом порядке.
assert (
    tuple(CHECKLIST.keys()) == ZONE_ORDER
), "Ключи CHECKLIST должны идти в каноническом ZONE_ORDER"
