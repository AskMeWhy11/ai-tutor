"""Подстановка контента кейса в промпт-шаблоны.

Промпты хранятся с плейсхолдерами {FACTS}/{DIALOGUES}, а контент
(facts.md / dialogues.md) подставляется в момент использования —
так правка контента сразу влияет на диалог без пересохранения промптов.
"""

from __future__ import annotations

import re
from typing import Final

from infrastructure.content.case_loader import load_case, resolve_case_id
from infrastructure.content.registry import case_label

__all__ = ["PLACEHOLDERS", "render_prompt"]

PLACEHOLDERS: Final[tuple[str, ...]] = ("PRODUCT", "FACTS", "DIALOGUES")

_PATTERN: Final[re.Pattern[str]] = re.compile(r"\{(" + "|".join(PLACEHOLDERS) + r")\}")


def render_prompt(template: str, case_id: str | None = None) -> str:
    """Заменить {FACTS}/{DIALOGUES} на контент кейса.

    Любые другие фигурные скобки (в т.ч. {{...}} JSON-литералы квиза)
    остаются нетронутыми — в отличие от str.format.
    """
    if not template or "{" not in template:
        return template
    cid = resolve_case_id(case_id)
    case = load_case(cid)
    values = {
        "PRODUCT": case_label(cid),
        "FACTS": case.facts or "(фактология не загружена)",
        "DIALOGUES": case.dialogues or "(образцовые диалоги не загружены)",
    }
    return _PATTERN.sub(lambda m: values[m.group(1)], template)
