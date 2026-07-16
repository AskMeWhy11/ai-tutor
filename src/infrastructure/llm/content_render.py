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

# Жирный/курсив markdown в исходных .md-файлах контента нужен только для
# удобства редактирования в UI. В промпт для LLM он попадать не должен —
# иначе модель иногда копирует ** дословно вместе с "сохрани все факты".
_BOLD_PATTERN: Final[re.Pattern[str]] = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_PATTERN: Final[re.Pattern[str]] = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")


def _strip_markdown_emphasis(text: str) -> str:
    text = _BOLD_PATTERN.sub(r"\1", text)
    text = _ITALIC_PATTERN.sub(r"\1", text)
    return text


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
        "FACTS": _strip_markdown_emphasis(case.facts) if case.facts else "(фактология не загружена)",
        "DIALOGUES": _strip_markdown_emphasis(case.dialogues)
        if case.dialogues
        else "(образцовые диалоги не загружены)",
    }
    return _PATTERN.sub(lambda m: values[m.group(1)], template)
