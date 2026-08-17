"""Экспорт промптов и переменных кейса в YAML эталонного формата.

Структура и нейминг — строго по образцам prompts.txt / variables.txt
параллельной ветки:

    prompts:
      map:
        <case-slug>-<назначение>-prompt: |
          <текст>

    variables:
      map:
        <kebab-key>: "<однострочное значение с \\n>"

pyyaml не используется: генерация выполняется вручную, чтобы формат
(4-пробельный отступ ключей, блочный скаляр ``|`` у промптов,
однострочные кавычки у переменных) в точности совпадал с эталоном.
"""

from __future__ import annotations

import json

from domain.states import Mode
from infrastructure.llm.prompt_store import PromptStore
from infrastructure.llm.variables import VARIABLES_MAP, resolve_variable

__all__ = ["case_slug", "export_prompts_yaml", "export_variables_yaml"]


def case_slug(case_id: str) -> str:
    return case_id.replace("_", "-")


def _block_scalar(text: str, indent: str = "      ") -> str:
    """Текст → YAML block scalar (содержимое ключа `key: |`)."""
    lines = text.rstrip("\n").split("\n")
    return "\n".join(indent + line if line.strip() else "" for line in lines)


def export_prompts_yaml(store: PromptStore, case_id: str) -> str:
    """prompts.map выбранного кейса: актуальные (отредактированные) тексты."""
    snap = store.snapshot(case_id)
    slug = case_slug(case_id)
    entries: tuple[tuple[str, str], ...] = (
        (f"{slug}-learning-transcription-prompt", snap.mode_prompts.get(Mode.TRAINING, "")),
        (f"{slug}-learning-quiz-transcription-prompt", snap.quiz_prompt),
        (f"{slug}-learning-check-prompt", snap.stage_director_prompt),
        (f"{slug}-client-transcription-prompt", snap.mode_prompts.get(Mode.EXAMPLE, "")),
        (f"{slug}-employee-transcription-prompt", snap.mode_prompts.get(Mode.PRACTICE, "")),
        (f"{slug}-mentor-transcription-prompt", snap.mode_prompts.get(Mode.KNOWLEDGE, "")),
        (
            f"{slug}-create-customer-profile-system-prompt",
            snap.customer_profile_system_prompt,
        ),
        (f"{slug}-create-customer-profile-user-prompt", snap.customer_profile_user_prompt),
    )
    out: list[str] = ["prompts:", "  map:"]
    for key, text in entries:
        out.append(f"    {key}: |")
        out.append(_block_scalar(text))
    return "\n".join(out) + "\n"


def export_variables_yaml(case_id: str) -> str:
    """variables.map выбранного кейса: значения из контента (facts/dialogues/...)."""
    out: list[str] = ["variables:", "  map:"]
    for key in VARIABLES_MAP:
        value = resolve_variable(key, case_id)
        # Однострочная строка в двойных кавычках с \n — как в эталоне.
        out.append(f"    {key}: {json.dumps(value, ensure_ascii=False)}")
    return "\n".join(out) + "\n"
