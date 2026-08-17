"""Подстановка контента кейса в промпт-шаблоны.

Промпты хранятся с плейсхолдерами эталонного нейминга ({PRODUCT_DETAILS},
{REAL_DIALOGUES}, ...), контент (facts.md / dialogues.md / checklist.json)
подставляется в момент использования — так правка контента сразу влияет на
диалог без пересохранения промптов.

Legacy-плейсхолдеры {PRODUCT}/{FACTS}/{DIALOGUES} поддерживаются для
промптов, сохранённых в admin до миграции на эталонный нейминг.
"""

from __future__ import annotations

import re
from typing import Final

from infrastructure.content.case_loader import resolve_case_id
from infrastructure.llm.variables import VARIABLES_MAP, placeholder_name, resolve_variable

__all__ = ["LEGACY_PLACEHOLDERS", "PLACEHOLDERS", "render_prompt", "strip_markdown_emphasis"]

# Эталонные плейсхолдеры — UPPER_SNAKE от kebab-ключей variables.map.
PLACEHOLDERS: Final[tuple[str, ...]] = tuple(placeholder_name(k) for k in VARIABLES_MAP)

# Старый нейминг → эталонный (для текстов, сохранённых до миграции).
LEGACY_PLACEHOLDERS: Final[dict[str, str]] = {
    "PRODUCT": "PRODUCT_NAME",
    "FACTS": "PRODUCT_DETAILS",
    "DIALOGUES": "REAL_DIALOGUES",
}

_ALL_NAMES: Final[tuple[str, ...]] = PLACEHOLDERS + tuple(LEGACY_PLACEHOLDERS)

_PATTERN: Final[re.Pattern[str]] = re.compile(r"\{(" + "|".join(_ALL_NAMES) + r")\}")

# Жирный/курсив markdown в исходных .md-файлах контента нужен только для
# удобства редактирования в UI. В промпт для LLM он попадать не должен —
# иначе модель иногда копирует ** дословно вместе с "сохрани все факты".
_BOLD_PATTERN: Final[re.Pattern[str]] = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_PATTERN: Final[re.Pattern[str]] = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")


def strip_markdown_emphasis(text: str) -> str:
    text = _BOLD_PATTERN.sub(r"\1", text)
    text = _ITALIC_PATTERN.sub(r"\1", text)
    return text


def _variable_key(placeholder: str) -> str:
    canonical = LEGACY_PLACEHOLDERS.get(placeholder, placeholder)
    return canonical.lower().replace("_", "-")


def render_prompt(template: str, case_id: str | None = None) -> str:
    """Заменить эталонные плейсхолдеры на значения переменных кейса.

    Любые другие фигурные скобки (в т.ч. {{...}} JSON-литералы квиза)
    остаются нетронутыми — в отличие от str.format.
    """
    if not template or "{" not in template:
        return template
    cid = resolve_case_id(case_id)

    def _sub(match: re.Match[str]) -> str:
        key = _variable_key(match.group(1))
        value = resolve_variable(key, cid)
        if key in ("product-details", "real-dialogues", "learning-details"):
            value = strip_markdown_emphasis(value)
        return value

    return _PATTERN.sub(_sub, template)
