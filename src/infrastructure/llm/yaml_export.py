"""Экспорт промптов и переменных кейса в YAML эталонного формата.

Структура и неймин — строго по образцам prompts.yaml эталонной ветки.

Эталонные суффиксы ключей (через case-slug):
  -start-notification-prompt
  -client-check-sales-prompt
  -employee-transcription-prompt
  -employee-check-sales-prompt
  -mentor-transcription-prompt
  -client-transcription-prompt
  -mentor-dialogue-completed-prompt
  -create-customer-profile-user-prompt
  -create-customer-profile-system-prompt
  -finish-notification-result-message-prompt
  -finish-notification-result-checklist-user-prompt
  -finish-notification-result-checklist-system-prompt

Обязательные переменные (контракт):
  {DIALOGUE_HISTORY}, {CLIENT_NAME}, {PROBLEM_ZONES}, {CHECKLIST},
  {PRODUCT_DETAILS}, {REAL_DIALOGUES}, {BASE_REQUIRE}, {CLIENT_AGE},
  {CLIENT_GENDER}, {CLIENT_CHARACTER}, {DECISION_STATUS}

Запрещённые самописные переменные: {PRODUCT_NAME}.
pyyaml не используется: генерация выполняется вручную, чтобы формат
(4-пробельный отступ ключей, блочный скаляр | у промптов,
однострочные кавычки у переменных) в точности совпадал с эталоном.
"""

from __future__ import annotations

import json
import re

from domain.states import Mode
from infrastructure.llm.export_service_prompts import SERVICE_PROMPTS
from infrastructure.llm.prompt_store import PromptStore
from infrastructure.llm.variables import VARIABLES_MAP, resolve_variable

__all__ = ["case_slug", "export_prompts_yaml", "export_variables_yaml"]


def case_slug(case_id: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_-]*", case_id):
        raise ValueError("Invalid product code")
    return case_id.replace("_", "-")


def _block_scalar(text: str, indent: str = "      ") -> str:
    """Текст -> YAML block scalar (содержимое ключа `key: |`)."""
    lines = text.rstrip("\n").split("\n")
    return "\n".join(indent + line if line.strip() else "" for line in lines)


_ALLOWED = frozenset(
    "CLIENT_NAME CLIENT_AGE CLIENT_CHARACTER CLIENT_GENDER BASE_REQUIRE PROBLEM_ZONES "
    "DIALOGUE_HISTORY REAL_DIALOGUES PRODUCT_DETAILS CHECKLIST DECISION_STATUS".split()
)


def _export_text(key: str, text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # The exported template has no runtime PRODUCT_NAME resolver.
    text = text.replace("{PRODUCT_NAME}", "продукт из раздела PRODUCT_DETAILS")
    if "create-customer-profile" in key:
        text = text.replace("тренажёра продаж", "учебного тренажёра")
        text = text.replace("продавать «", "обсуждать тему «")

    text = "\n".join(
        line.rstrip()
        for line in text.split("\n")
        if not line.strip().startswith(("```", "~~~")) and line.strip() != "codeNamemd"
    ).strip()
    if not text:
        raise ValueError(f"Empty export prompt: {key}")
    if key.endswith("-transcription-prompt"):
        if "КРИТЕРИИ ЗАВЕРШЕНИЯ СТАДИИ" in text:
            raise ValueError(f"Completion criteria in generation prompt: {key}")
        if "{DIALOGUE_HISTORY}" not in text:
            text += "\n\nДИАЛОГ:\n{DIALOGUE_HISTORY}"
        if "mentor-transcription" in key and "{PROBLEM_ZONES}" not in text:
            text += "\nПЕРСОНАЛЬНЫЕ ЗАДАНИЯ: {PROBLEM_ZONES}"
    if "продукт из раздела PRODUCT_DETAILS" in text and "{PRODUCT_DETAILS}" not in text:
        text += "\nПРОДУКТ: {PRODUCT_DETAILS}"
    unknown = set(re.findall(r"\{([A-Za-z_][A-Za-z_0-9]*)\}", text)) - _ALLOWED
    if unknown or re.search(r"\b(?:TRAINING|KNOWLEDGE|EXAMPLE|PRACTICE)\b", text):
        raise ValueError(f"Unsupported export contract in {key}: {sorted(unknown)}")
    if "codeNamemd" in text or "```" in text or "~~~" in text:
        raise ValueError(f"Unexpected wrapper in {key}")
    return text


def export_prompts_yaml(store: PromptStore, case_id: str) -> str:
    """prompts.map выбранного кейса в эталонной структуре.

    Порядок ключей и суффиксы воспроизводят эталон:
      -start-notification-prompt        (стартовое сообщение сессии)
      -client-check-sales-prompt        (проверка статуса — клиент)
      -employee-transcription-prompt    (генерация реплики — сотрудник/PRACTICE)
      -employee-check-sales-prompt      (проверка статуса — сотрудник)
      -mentor-transcription-prompt      (генерация реплики — ментор/KNOWLEDGE)
      -client-transcription-prompt      (генерация реплики — клиент/EXAMPLE)
      -mentor-dialogue-completed-prompt (проверка завершения диалога)
      -create-customer-profile-*        (генерация профиля клиента)
      -finish-notification-result-*     (итоговый отчёт сессии)

    Разделение ответственности строго:
      *-transcription-prompt        -- ТОЛЬКО генерация реплики
      *-check-sales-prompt          -- ТОЛЬКО проверка статуса завершения
      *-dialogue-completed-prompt   -- ТОЛЬКО проверка завершённости диалога
    """
    snap = store.snapshot(case_id)
    slug = case_slug(case_id)

    # Эталонный порядок ключей (совпадает с close-deposit-social-eng)
    entries: tuple[tuple[str, str], ...] = (
        (f"{slug}-start-notification-prompt", SERVICE_PROMPTS["start-notification-prompt"]),
        (f"{slug}-client-check-sales-prompt", SERVICE_PROMPTS["client-check-sales-prompt"]),
        (f"{slug}-employee-transcription-prompt", snap.mode_prompts.get(Mode.PRACTICE, "")),
        (f"{slug}-employee-check-sales-prompt", SERVICE_PROMPTS["employee-check-sales-prompt"]),
        (f"{slug}-mentor-transcription-prompt", snap.mode_prompts.get(Mode.KNOWLEDGE, "")),
        (f"{slug}-client-transcription-prompt", snap.mode_prompts.get(Mode.EXAMPLE, "")),
        (
            f"{slug}-mentor-dialogue-completed-prompt",
            SERVICE_PROMPTS["mentor-dialogue-completed-prompt"],
        ),
        (f"{slug}-create-customer-profile-user-prompt", snap.customer_profile_user_prompt),
        (
            f"{slug}-create-customer-profile-system-prompt",
            snap.customer_profile_system_prompt,
        ),
        (
            f"{slug}-finish-notification-result-message-prompt",
            SERVICE_PROMPTS["finish-notification-result-message-prompt"],
        ),
        (
            f"{slug}-finish-notification-result-checklist-user-prompt",
            SERVICE_PROMPTS["finish-notification-result-checklist-user-prompt"],
        ),
        (
            f"{slug}-finish-notification-result-checklist-system-prompt",
            SERVICE_PROMPTS["finish-notification-result-checklist-system-prompt"],
        ),
    )
    out: list[str] = ["prompts:", "  map:"]
    for key, text in entries:
        text = _export_text(key, text)
        out.append(f"    {key}: |")
        out.append(_block_scalar(text))
    return "\n".join(out) + "\n"


def export_variables_yaml(case_id: str) -> str:
    """variables.map выбранного кейса: значения из контента (facts/dialogues/...)."""
    out: list[str] = ["variables:", "  map:"]
    for key in VARIABLES_MAP:
        value = resolve_variable(key, case_id)
        # Однострочная строка в двойных кавычках с \n -- как в эталоне.
        out.append(f"    {key}: {json.dumps(value, ensure_ascii=False)}")
    return "\n".join(out) + "\n"
