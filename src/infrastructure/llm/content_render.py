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

__all__ = [
    "LEGACY_PLACEHOLDERS",
    "PLACEHOLDERS",
    "PROFILE_PLACEHOLDERS",
    "STEP_PLACEHOLDERS",
    "apply_profile",
    "apply_step",
    "render_prompt",
    "strip_markdown_emphasis",
]

# Эталонные плейсхолдеры — UPPER_SNAKE от kebab-ключей variables.map.
PLACEHOLDERS: Final[tuple[str, ...]] = tuple(placeholder_name(k) for k in VARIABLES_MAP)

# Плейсхолдеры профиля клиента (эталон: create-customer-profile).
# Значения приходят не из контента кейса, а из сгенерированного профиля,
# поэтому подставляются отдельным проходом (apply_profile).
PROFILE_PLACEHOLDERS: Final[tuple[str, ...]] = (
    "CLIENT_NAME",
    "CLIENT_AGE",
    "CLIENT_GENDER",
    "CLIENT_CHARACTER",
    "BASE_REQUIRE",
)

# Нейтральный профиль на случай, когда генератор ещё не отработал.
PROFILE_DEFAULTS: Final[dict[str, str]] = {
    "CLIENT_NAME": "Клиент",
    "CLIENT_AGE": "35",
    "CLIENT_GENDER": "м",
    "CLIENT_CHARACTER": "нейтральный, отвечает по ситуации",
    "BASE_REQUIRE": "интересуется продуктом, потребность пока не раскрыта",
}

_PROFILE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\{(" + "|".join(PROFILE_PLACEHOLDERS) + r")\}"
)

# Контекстные плейсхолдеры TRAINING-flow (эталон: STEP/STEP_STATUS).
# Значение зависит от текущего FSM-состояния сессии, а не от контента кейса,
# поэтому подставляется отдельным проходом (apply_step) в момент вызова LLM.
STEP_PLACEHOLDERS: Final[tuple[str, ...]] = ("STEP", "STEP_STATUS")

_STEP_PATTERN: Final[re.Pattern[str]] = re.compile(r"\{(" + "|".join(STEP_PLACEHOLDERS) + r")\}")

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


def apply_profile(text: str, profile: dict[str, str] | None) -> str:
    """Подставить {CLIENT_*}/{BASE_REQUIRE} из профиля клиента.

    Профиль не задан → нейтральные значения (PROFILE_DEFAULTS), чтобы
    плейсхолдеры не утекали в LLM.
    """
    if not text or "{" not in text:
        return text
    values = {**PROFILE_DEFAULTS, **(profile or {})}
    return _PROFILE_PATTERN.sub(lambda m: values.get(m.group(1), m.group(0)), text)


def apply_step(text: str, step: str, step_status: str = "") -> str:
    """Подставить {STEP}/{STEP_STATUS} текущего этапа TRAINING-flow."""
    if not text or "{" not in text:
        return text
    values = {"STEP": step, "STEP_STATUS": step_status}
    return _STEP_PATTERN.sub(lambda m: values.get(m.group(1), m.group(0)), text)
