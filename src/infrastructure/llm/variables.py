"""Реестр переменных промптов (эталон: variables.map параллельной ветки).

Ключи — kebab-case (как в variables.map), плейсхолдеры в текстах промптов —
UPPER_SNAKE от тех же ключей: product-details → {PRODUCT_DETAILS}.

Значения не хранятся здесь дословно (в отличие от эталонного YAML):
источником остаётся контент кейса (cases/<id>/facts.md и т.д.) — так правка
контента в админке сразу влияет на промпты.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

from infrastructure.content.case_loader import load_case
from infrastructure.content.registry import case_product_name

__all__ = [
    "VARIABLES_MAP",
    "placeholder_name",
    "resolve_variable",
]


def _product_details(case_id: str) -> str:
    facts = load_case(case_id).facts
    return facts if facts else "(фактология не загружена)"


def _real_dialogues(case_id: str) -> str:
    dialogues = load_case(case_id).dialogues
    return dialogues if dialogues else "(образцовые диалоги не загружены)"


def _learning_check_list(case_id: str) -> str:
    """Контрольные вопросы LEARNING_CHECK: критерии чек-листа кейса."""
    checklist = load_case(case_id).checklist
    lines: list[str] = []
    n = 0
    for zone_items in checklist.values():
        for item in zone_items:
            n += 1
            lines.append(f"{n}. {item.name}: {item.criteria}")
    return "\n".join(lines) if lines else "(контрольные вопросы не заданы)"


def _count_of_questions(case_id: str) -> str:
    from domain.constants import TRAINING_QUIZ_QUESTIONS

    return str(TRAINING_QUIZ_QUESTIONS)


def _checklist(case_id: str) -> str:
    checklist = load_case(case_id).checklist
    lines: list[str] = []
    for zone_items in checklist.values():
        for item in zone_items:
            lines.append(f"{item.id}. {item.name} — {item.criteria}")
    return "\n".join(lines) if lines else "(чек-лист не загружен)"


# variables.map: kebab-ключ → резолвер значения из контента кейса.
# learning-details — алиас product-details: в этой ветке фактология едина
# для обучения и практики (facts.md).
VARIABLES_MAP: Final[dict[str, Callable[[str], str]]] = {
    "product-name": case_product_name,
    "product-details": _product_details,
    "real-dialogues": _real_dialogues,
    "learning-details": _product_details,
    "checklist": _checklist,
    "learning-check-list": _learning_check_list,
    "count-of-questions": _count_of_questions,
}


def placeholder_name(variable_key: str) -> str:
    """kebab-ключ переменной → имя плейсхолдера: product-details → PRODUCT_DETAILS."""
    return variable_key.replace("-", "_").upper()


def resolve_variable(variable_key: str, case_id: str) -> str:
    resolver = VARIABLES_MAP.get(variable_key)
    if resolver is None:
        raise KeyError(f"Неизвестная переменная {variable_key!r}")
    return resolver(case_id)
