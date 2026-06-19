"""Stub-реализация аватара. Возвращает реплики из контента по текущему FSMState."""

from __future__ import annotations

from domain.context import SessionContext
from domain.states import FSMState
from domain.types import ZONE_ORDER, Zone
from infrastructure.content.cc_novichok import (
    EXAMPLE_DIALOGUE,
    KNOWLEDGE_BLOCKS,
    PRACTICE_SCENARIO,
    START_MESSAGE,
    TRAINING_BLOCKS,
)
from infrastructure.llm.prompt_store import PromptStore


class StubAvatar:
    """Детерминированный аватар без LLM. Используется для демо и fallback."""

    def __init__(self, prompt_store: PromptStore) -> None:
        self._prompts = prompt_store

    async def next_message(self, state: FSMState, ctx: SessionContext) -> str:
        match state:
            case FSMState.WELCOME:
                tpl = self._prompts.get_template(FSMState.WELCOME)
                return tpl if tpl.strip() else START_MESSAGE

            case FSMState.TRAINING:
                # Если истории нет — отдаём первый блок теории.
                # На последующих user-репликах — подтверждаем и предлагаем продолжить/проверить.
                user_turns = sum(1 for m in ctx.dialog_history if m.role == "user")
                if user_turns == 0:
                    return TRAINING_BLOCKS[0].text
                idx = min(user_turns, len(TRAINING_BLOCKS) - 1)
                if user_turns >= len(TRAINING_BLOCKS):
                    return (
                        "Это вся теория, что я готовил. Если всё понятно — "
                        "нажми «Теория изучена», и проверим тебя вопросами."
                    )
                return TRAINING_BLOCKS[idx].text

            case FSMState.TRAINING_QUIZ:
                idx = self._safe_quiz_index(ctx)
                return TRAINING_BLOCKS[idx].question

            case FSMState.TRAINING_EXPLAIN:
                idx = self._safe_quiz_index(ctx)
                block = TRAINING_BLOCKS[idx]
                return (
                    f"Не совсем так. Правильный ответ: {block.correct_answer} "
                    f"Давай попробуем ещё раз."
                )

            case FSMState.EXAMPLE:
                # Стартовая реплика — первая зона. Дальше — следующая по индексу
                # числа user-реплик, иначе финальная подсказка.
                user_turns = sum(1 for m in ctx.dialog_history if m.role == "user")
                if user_turns >= len(ZONE_ORDER):
                    return (
                        "Видишь схему? Сначала потребность, потом — продукт под неё, "
                        "потом — снятие возражений. Готов попробовать сам? "
                        "Жми «Пример завершён»."
                    )
                zone = ZONE_ORDER[user_turns] if user_turns > 0 else self._zone_for_cycle(ctx)
                turn = EXAMPLE_DIALOGUE[zone]
                return f"💬 Клиент: {turn.client_line}\n\n👤 Сотрудник: {turn.employee_line}"

            case FSMState.PRACTICE:
                user_turns = sum(1 for m in ctx.dialog_history if m.role == "user")
                if user_turns >= len(ZONE_ORDER):
                    return (
                        "Хорошо, я понял. Думаю, мне подходит эта карта. "
                        "Жми «Диалог завершён» — посмотрим, что получилось."
                    )
                zone = ZONE_ORDER[user_turns] if user_turns > 0 else self._zone_for_cycle(ctx)
                return f"💬 Клиент: {PRACTICE_SCENARIO[zone].client_line}"

            case FSMState.PRACTICE_PARTIAL:
                if ctx.weak_zones_remaining:
                    zones = ", ".join(self._zone_label(z) for z in ctx.weak_zones_remaining)
                    return (
                        f"Практику прошли. Я заметил пробелы в зонах: "
                        f"{zones}. Давай их подтянем — будет легче в следующий раз."
                    )
                return "Практику прошли, но есть что улучшить."

            case FSMState.KNOWLEDGE:
                user_turns = sum(1 for m in ctx.dialog_history if m.role == "user")
                weak_zones = ctx.weak_zones_remaining
                if not weak_zones:
                    return "Все слабые зоны разобрали. Жми «Зоны проработаны»."
                if user_turns >= len(weak_zones):
                    return (
                        "Прошли все западающие зоны. Готов снова попробовать практику? "
                        "Нажми «Зоны проработаны»."
                    )
                zone_key = weak_zones[user_turns]
                if zone_key in ZONE_ORDER and zone_key in KNOWLEDGE_BLOCKS:
                    return KNOWLEDGE_BLOCKS[zone_key]
                return "Все слабые зоны разобрали."

        tpl = self._prompts.get_template(state)
        return tpl if tpl.strip() else "..."

    async def next_hint(self, state: FSMState, ctx: SessionContext) -> str | None:
        if state is not FSMState.EXAMPLE:
            return None
        zone = self._zone_for_cycle(ctx)
        turn = EXAMPLE_DIALOGUE.get(zone)
        if turn is None or not turn.rationale.strip():
            return None
        return turn.rationale

    @staticmethod
    def _safe_quiz_index(ctx: SessionContext) -> int:
        idx = ctx.quiz_question_index
        return max(0, min(idx, len(TRAINING_BLOCKS) - 1))

    @staticmethod
    def _zone_for_cycle(ctx: SessionContext) -> Zone:
        idx = ctx.cycle_count % len(ZONE_ORDER)
        return ZONE_ORDER[idx]

    @staticmethod
    def _zone_label(zone: str) -> str:
        labels = {
            "needs": "выявление потребности",
            "pitch": "презентация продукта",
            "conditions": "условия и возражения",
        }
        return labels.get(zone, zone)
