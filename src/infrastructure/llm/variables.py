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
}


def placeholder_name(variable_key: str) -> str:
    """kebab-ключ переменной → имя плейсхолдера: product-details → PRODUCT_DETAILS."""
    return variable_key.replace("-", "_").upper()


def resolve_variable(variable_key: str, case_id: str) -> str:
    resolver = VARIABLES_MAP.get(variable_key)
    if resolver is None:
        raise KeyError(f"Неизвестная переменная {variable_key!r}")
    return resolver(case_id)
