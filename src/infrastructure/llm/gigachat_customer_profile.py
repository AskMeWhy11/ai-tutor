"""GigaChat-генератор профиля клиента (эталон: create-customer-profile).

Использует system/user-пару промптов из PromptStore (редактируется в админке),
ожидает от модели строгий JSON. При любой ошибке — fallback на stub.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

from application.ports.customer_profile import CustomerProfile, CustomerProfileGenerator
from infrastructure.llm.prompt_store import PromptStore

if TYPE_CHECKING:
    from gigachat import GigaChat

__all__ = ["GigaChatCustomerProfileGenerator"]

logger = logging.getLogger(__name__)


class GigaChatCustomerProfileGenerator:
    def __init__(
        self,
        client: GigaChat,
        prompt_store: PromptStore,
        fallback: CustomerProfileGenerator,
        model: str | None = None,
    ) -> None:
        self._client = client
        self._prompt_store = prompt_store
        self._fallback = fallback
        self._model = model

    async def generate(self, *, case_id: str | None = None) -> CustomerProfile:
        system, user = self._prompt_store.get_customer_profile_prompts(case_id)
        try:
            raw = await self._chat([("system", system), ("user", user)])
        except Exception:
            logger.exception("LLM profile generator failed, fallback to stub")
            return await self._fallback.generate(case_id=case_id)

        profile = _parse_profile(raw)
        if profile is None:
            logger.warning("LLM profile returned unparseable: %r → fallback", raw)
            return await self._fallback.generate(case_id=case_id)
        return profile

    async def _chat(self, messages: list[tuple[str, str]]) -> str:
        from gigachat.models import Chat, Messages, MessagesRole

        role_map = {
            "system": MessagesRole.SYSTEM,
            "user": MessagesRole.USER,
        }
        payload = Chat(
            messages=[Messages(role=role_map[role], content=content) for role, content in messages],
        )
        if self._model:
            payload.model = self._model
        resp = await self._client.achat(payload)
        choices = getattr(resp, "choices", None) or []
        if not choices:
            return ""
        message = getattr(choices[0], "message", None)
        return str(getattr(message, "content", "") if message else "").strip()


def _parse_profile(raw: str) -> CustomerProfile | None:
    parsed = _extract_json(raw)
    if parsed is None:
        return None
    name = str(parsed.get("client_name", "")).strip()
    character = str(parsed.get("client_character", "")).strip()
    base_require = str(parsed.get("base_require", "")).strip()
    if not (name and character and base_require):
        return None
    try:
        age = int(str(parsed.get("client_age", 0)))
    except (TypeError, ValueError):
        return None
    if not 18 <= age <= 99:
        return None
    gender = str(parsed.get("client_gender", "")).strip().lower()
    if gender not in ("м", "ж"):
        return None
    return CustomerProfile(
        client_name=name[:50],
        client_age=age,
        client_gender=gender,
        client_character=character[:200],
        base_require=base_require[:500],
    )


def _extract_json(raw: str) -> dict[str, object] | None:
    """Достать JSON-объект из ответа LLM. Терпит markdown-обёртку и мусор."""
    if not raw:
        return None
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        obj = json.loads(match.group(0))
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None
