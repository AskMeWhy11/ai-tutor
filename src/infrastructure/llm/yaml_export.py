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

from domain.states import Mode
from infrastructure.llm.default_prompts import embed_stage_criteria
from infrastructure.llm.prompt_store import PromptStore
from infrastructure.llm.variables import VARIABLES_MAP, resolve_variable

__all__ = ["case_slug", "export_prompts_yaml", "export_variables_yaml"]


def case_slug(case_id: str) -> str:
    return case_id.replace("_", "-")


def _block_scalar(text: str, indent: str = "      ") -> str:
    """Текст -> YAML block scalar (содержимое ключа `key: |`)."""
    lines = text.rstrip("\n").split("\n")
    return "\n".join(indent + line if line.strip() else "" for line in lines)


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

    def with_criteria(mode: Mode) -> str:
        return embed_stage_criteria(
            snap.mode_prompts.get(mode, ""),
            snap.stage_director_prompts.get(mode, ""),
            slug,
        )

    # Эталонный порядок ключей (совпадает с close-deposit-social-eng)
    entries: tuple[tuple[str, str], ...] = (
        (f"{slug}-start-notification-prompt", snap.start_notification_prompt),
        (f"{slug}-client-check-sales-prompt", snap.client_check_sales_prompt),
        (f"{slug}-employee-transcription-prompt", with_criteria(Mode.PRACTICE)),
        (f"{slug}-employee-check-sales-prompt", snap.employee_check_sales_prompt),
        (f"{slug}-mentor-transcription-prompt", with_criteria(Mode.KNOWLEDGE)),
        (f"{slug}-client-transcription-prompt", with_criteria(Mode.EXAMPLE)),
        (f"{slug}-mentor-dialogue-completed-prompt", snap.mentor_dialogue_completed_prompt),
        (f"{slug}-create-customer-profile-user-prompt", snap.customer_profile_user_prompt),
        (
            f"{slug}-create-customer-profile-system-prompt",
            snap.customer_profile_system_prompt,
        ),
        (
            f"{slug}-finish-notification-result-message-prompt",
            snap.finish_notification_result_message_prompt,
        ),
        (
            f"{slug}-finish-notification-result-checklist-user-prompt",
            snap.finish_notification_result_checklist_user_prompt,
        ),
        (
            f"{slug}-finish-notification-result-checklist-system-prompt",
            snap.finish_notification_result_checklist_system_prompt,
        ),
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
        # Однострочная строка в двойных кавычках с \n -- как в эталоне.
        out.append(f"    {key}: {json.dumps(value, ensure_ascii=False)}")
    return "\n".join(out) + "\n"
