"""GigaChat-реализация аватара.

Стратегия:
- Для режимных состояний (TRAINING / EXAMPLE / PRACTICE / KNOWLEDGE) —
  полноценный многошаговый диалог: системный промпт режима + история
  ctx.dialog_history + (опционально) служебная подсказка с фактологией
  (например, список западающих зон для KNOWLEDGE). Если в истории нет
  user-реплик — генерируем стартовое сообщение от аватара.
- Для статичных состояний (WELCOME, *_DONE, SKIP_WARNING_*, FINISH и т.п.)
  LLM перефразирует базовый шаблон от лица наставника. Базовый текст
  берётся из stub'а (тот в свою очередь читает PromptStore.templates).
- Если system_prompt режима пуст или вызов LLM падает — graceful fallback
  на stub-реплику.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from domain.context import SessionContext
from domain.states import FSMState, Mode
from infrastructure.llm.content_render import apply_step, strip_emotion_tags
from infrastructure.llm.prompt_store import PromptStore
from infrastructure.llm.stub_avatar import StubAvatar
from infrastructure.llm.training_steps import training_step

if TYPE_CHECKING:
    from gigachat import GigaChat

logger = logging.getLogger(__name__)

__all__ = ["GigaChatAvatar"]


# Маппинг FSM-состояния → режим, чей system_prompt используется.
_STATE_TO_MODE: dict[FSMState, Mode] = {
    FSMState.TRAINING: Mode.TRAINING,
    # Этап LEARNING_CHECK: технические узлы квиза ведёт тот же TRAINING-промпт.
    FSMState.TRAINING_QUIZ: Mode.TRAINING,
    FSMState.TRAINING_EXPLAIN: Mode.TRAINING,
    FSMState.EXAMPLE: Mode.EXAMPLE,
    FSMState.PRACTICE: Mode.PRACTICE,
    FSMState.KNOWLEDGE: Mode.KNOWLEDGE,
}

# Промпт-обёртка для статичных состояний (перефразирование).
_STATIC_USER_TEMPLATE = (
    "Контекст обучения:\n"
    "- сотрудник: {employee}\n"
    "- продукт: {product}\n"
    "- состояние FSM: {state}\n"
    "- цикл практики: {cycle}\n\n"
    "Базовая реплика (её смысл и факты должны быть сохранены):\n"
    "---\n{base}\n---\n\n"
    "Перескажи реплику от лица наставника-аватара: тёпло, кратко, "
    "с сохранением всех фактов и цифр. Без markdown-разметки."
)

# Стартовая «затравка» для режима, если истории ещё нет.
_KICKOFF_PROMPTS: dict[Mode, str] = {
    Mode.TRAINING: (
        "Сотрудник {employee} только что зашёл в режим обучения. "
        "Поздоровайся и начни рассказывать теорию по продукту с первого "
        "блока фактологии. В конце реплики дай сотруднику возможность "
        "задать вопрос или попросить продолжить."
    ),
    Mode.EXAMPLE: (
        "Сотрудник {employee} только что зашёл в режим «Пример» и играет "
        "роль клиента. Начни диалог: коротко поздоровайся как сотрудник "
        "банка и задай первый открытый вопрос для выявления потребности."
    ),
    Mode.PRACTICE: (
        "Сотрудник {employee} только что зашёл в режим «Практика» и играет "
        "роль продавца. Ты — клиент с одной из легенд. Начни диалог "
        "коротко, как живой клиент: обозначь свою проблему общими словами, "
        "без раскрытия деталей."
    ),
    Mode.KNOWLEDGE: (
        "Сотрудник {employee} зашёл в режим «Знания». Западающие зоны "
        "из практики: {weak_zones}. Поздоровайся, кратко обозначь, какие "
        "зоны будем подтягивать, и начни с первой: дай объяснение и задай "
        "тренировочный вопрос."
    ),
}


class GigaChatAvatar:
    def __init__(
        self,
        client: GigaChat,
        prompt_store: PromptStore,
        fallback: StubAvatar,
        model: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._client = client
        self._prompts = prompt_store
        self._fallback = fallback
        self._model = model
        self._timeout = timeout

    async def next_message(self, state: FSMState, ctx: SessionContext) -> str:
        mode = _STATE_TO_MODE.get(state)
        if mode is not None:
            return await self._handle_mode(mode, state, ctx)
        return await self._handle_static(state, ctx)

    async def next_hint(self, state: FSMState, ctx: SessionContext) -> str | None:
        # Подсказки берём из контента (rationale) — LLM здесь не нужен.
        return await self._fallback.next_hint(state, ctx)

    # ------------------------------------------------------------------
    # Режимные состояния — реальный диалог с историей
    # ------------------------------------------------------------------

    async def _handle_mode(
        self,
        mode: Mode,
        state: FSMState,
        ctx: SessionContext,
    ) -> str:
        mode_prompt = self._prompts.get_mode_prompt(mode, ctx.product_id).strip()
        if not mode_prompt:
            logger.info("mode_prompt пуст для %s — fallback на stub", mode)
            return await self._fallback.next_message(state, ctx)
        if mode is Mode.TRAINING:
            mode_prompt = apply_step(mode_prompt, training_step(state, ctx))

        system_prompt = self._compose_system_prompt(mode_prompt, ctx)
        history = ctx.dialog_history

        if not any(m.role == "user" for m in history):
            # Старт режима: используем kickoff как первое user-сообщение.
            kickoff = _KICKOFF_PROMPTS[mode].format(
                employee=ctx.employee_name or "сотрудник",
                weak_zones=", ".join(ctx.weak_zones_remaining) or "—",
            )
            messages = [
                ("system", system_prompt),
                ("user", kickoff),
            ]
        else:
            messages = [("system", system_prompt)]
            for msg in history:
                role = "user" if msg.role == "user" else "assistant"
                messages.append((role, msg.text))

        try:
            text = await self._chat(messages)
        except Exception:
            logger.exception("GigaChat call failed for mode=%s, fallback to stub", mode)
            return await self._fallback.next_message(state, ctx)

        if not text:
            return await self._fallback.next_message(state, ctx)
        # Теги эмоций нужны сценарию реплики, но интерфейс их не разбирает.
        cleaned = strip_emotion_tags(text)
        if not cleaned:
            return await self._fallback.next_message(state, ctx)
        return cleaned

    def _compose_system_prompt(self, mode_prompt: str, ctx: SessionContext) -> str:
        global_prompt = self._prompts.snapshot().system_prompt.strip()
        ctx_block = (
            "\n\nКОНТЕКСТ СЕССИИ:\n"
            f"- сотрудник: {ctx.employee_name or '—'}\n"
            f"- продукт: {ctx.product_id or '—'}\n"
            f"- цикл практики: {ctx.cycle_count}\n"
        )
        if ctx.weak_zones_remaining:
            ctx_block += f"- западающие зоны: {', '.join(ctx.weak_zones_remaining)}\n"

        # mode_prompt уже содержит фактологию/диалоги (render_prompt в PromptStore),
        # поэтому отдельный content_block больше не нужен — избегаем дублирования.
        parts = [mode_prompt, ctx_block]
        if global_prompt:
            parts.insert(0, f"{global_prompt}\n\n")
        return "".join(parts)

    # ------------------------------------------------------------------
    # Статичные состояния — перефразирование
    # ------------------------------------------------------------------

    async def _handle_static(self, state: FSMState, ctx: SessionContext) -> str:
        base = await self._fallback.next_message(state, ctx)
        if not base or not base.strip():
            return base

        system_prompt = self._prompts.snapshot().system_prompt.strip()
        if not system_prompt:
            return base

        user_msg = _STATIC_USER_TEMPLATE.format(
            employee=ctx.employee_name or "—",
            product=ctx.product_id or "—",
            state=state.value,
            cycle=ctx.cycle_count,
            base=base,
        )

        try:
            text = await self._chat(
                [
                    ("system", system_prompt),
                    ("user", user_msg),
                ]
            )
        except Exception:
            logger.exception("GigaChat call failed for state=%s, fallback to base", state)
            return base
        return text or base

    # ------------------------------------------------------------------
    # Низкоуровневый вызов
    # ------------------------------------------------------------------

    async def _chat(self, messages: list[tuple[str, str]]) -> str:
        from gigachat.models import Chat, Messages, MessagesRole

        def _role(name: str) -> Any:
            # MessagesRole в разных версиях SDK имеет разный набор констант.
            # Если ASSISTANT отсутствует — отдаём строку, SDK её принимает.
            attr = getattr(MessagesRole, name.upper(), None)
            return attr if attr is not None else name.lower()

        payload = Chat(
            messages=[Messages(role=_role(role), content=content) for role, content in messages],
        )
        if self._model:
            payload.model = self._model

        resp = await self._client.achat(payload)
        choices = getattr(resp, "choices", None) or []
        if not choices:
            return ""
        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", "") if message else ""
        return str(content).strip()
