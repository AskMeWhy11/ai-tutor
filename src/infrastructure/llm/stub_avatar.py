"""Stub-реализация аватара. Возвращает реплики из контента по текущему FSMState.

Важно: EXAMPLE_DIALOGUE / PRACTICE_SCENARIO / KNOWLEDGE_BLOCKS / TRAINING_BLOCKS —
это курированный контент cc_novichok. Для остальных кейсов (техники продаж) его
отдавать НЕЛЬЗЯ: иначе при падении LLM в диалог про, например, ХПВ прилетает
текст про СберКарту. Для них теорию собираем из facts.md самого кейса, а для
ролевых состояний отдаём нейтральные реплики без чужой фактологии.
"""

from __future__ import annotations

import re

from domain.context import SessionContext
from domain.states import FSMState
from domain.types import ZONE_ORDER, Zone
from infrastructure.content.case_loader import load_case, resolve_case_id
from infrastructure.content.cc_novichok import (
    EXAMPLE_DIALOGUE,
    KNOWLEDGE_BLOCKS,
    PRACTICE_SCENARIO,
    START_MESSAGE,
    TRAINING_BLOCKS,
)
from infrastructure.content.registry import DEFAULT_CASE_ID
from infrastructure.llm.content_render import strip_markdown_emphasis
from infrastructure.llm.prompt_store import PromptStore

# Фактология кейса — нумерованный список верхнего уровня; вложенные строки
# (таблицы, под-пункты) идут с отступом и остаются в своём пункте.
_FACT_ITEM_SPLIT = re.compile(r"(?m)^(?=\d+\.\s)")
_LEADING_NUMBER = re.compile(r"^\d+\.\s*")


def _theory_blocks(case_id: str) -> tuple[str, ...]:
    """Блоки теории для stub-режима TRAINING.

    cc_novichok — курированные TRAINING_BLOCKS. Остальные кейсы — пункты
    их собственного facts.md (чужой контент подмешивать нельзя).

    Не кэшируем: load_case уже под lru_cache и инвалидируется при правке
    контента в админке; парсинг здесь дешёвый.

    Текст стаба уходит в чат напрямую, минуя LLM, поэтому чистим markdown
    и служебную нумерацию пунктов — сотруднику их видеть не нужно.
    """
    if case_id == DEFAULT_CASE_ID:
        return tuple(b.text for b in TRAINING_BLOCKS)
    facts = load_case(case_id).facts
    if not facts.strip():
        return ()
    out: list[str] = []
    for chunk in _FACT_ITEM_SPLIT.split(facts):
        block = chunk.strip()
        if not block or not block[0].isdigit():
            continue
        block = strip_markdown_emphasis(_LEADING_NUMBER.sub("", block))
        if block.strip():
            out.append(block.strip())
    return tuple(out)


class StubAvatar:
    """Детерминированный аватар без LLM. Используется для демо и fallback."""

    def __init__(self, prompt_store: PromptStore) -> None:
        self._prompts = prompt_store

    async def next_message(self, state: FSMState, ctx: SessionContext) -> str:
        is_cc = resolve_case_id(ctx.product_id) == DEFAULT_CASE_ID

        match state:
            case FSMState.WELCOME:
                tpl = self._prompts.get_template(FSMState.WELCOME)
                return tpl if tpl.strip() else START_MESSAGE

            case FSMState.TRAINING:
                # Если истории нет — отдаём первый блок теории.
                # На последующих user-репликах — подтверждаем и предлагаем продолжить/проверить.
                blocks = _theory_blocks(resolve_case_id(ctx.product_id))
                if not blocks:
                    return "Секунду, не могу подгрузить теорию. Попробуй написать ещё раз."
                user_turns = sum(1 for m in ctx.dialog_history if m.role == "user")
                if user_turns == 0:
                    return blocks[0]
                if user_turns >= len(blocks):
                    return (
                        "Это вся теория, что я готовил. Если всё понятно — "
                        "нажми «Теория изучена», и проверим тебя вопросами."
                    )
                return blocks[user_turns]

            case FSMState.TRAINING_QUIZ:
                if not is_cc:
                    # Вопросы по чужой фактологии задавать нельзя.
                    return "Секунду, вопрос готовится. Напиши что-нибудь, чтобы продолжить."
                idx = self._safe_quiz_index(ctx)
                return TRAINING_BLOCKS[idx].question

            case FSMState.TRAINING_EXPLAIN:
                if not is_cc:
                    return "Давай попробуем ещё раз."
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
                if not is_cc:
                    # EXAMPLE_DIALOGUE — реплики про кредитную карту, для
                    # техник продаж это чужой контент.
                    return "Секунду, подбираю пример. Напиши что-нибудь, чтобы продолжить."
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
                if not is_cc:
                    return "💬 Клиент: Расскажите подробнее, что вы предлагаете?"
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
                # next(...) вместо `in ZONE_ORDER`: типобезопасно в любых версиях mypy.
                weak_zone: Zone | None = next((z for z in ZONE_ORDER if z == zone_key), None)
                if weak_zone is not None:
                    if is_cc and weak_zone in KNOWLEDGE_BLOCKS:
                        return KNOWLEDGE_BLOCKS[weak_zone]
                    if not is_cc:
                        # KNOWLEDGE_BLOCKS — разбор зон на примере кредитной карты.
                        return (
                            f"Давай разберём зону «{self._zone_label(weak_zone)}». "
                            "В чём, по-твоему, была сложность?"
                        )
                return "Все слабые зоны разобрали."

        tpl = self._prompts.get_template(state)
        return tpl if tpl.strip() else "..."

    async def next_hint(self, state: FSMState, ctx: SessionContext) -> str | None:
        if state is not FSMState.EXAMPLE:
            return None
        # EXAMPLE_DIALOGUE (и его rationale-подсказки) — контент cc_novichok.
        # Для техник продаж эту подсказку не показываем вовсе.
        if resolve_case_id(ctx.product_id) != DEFAULT_CASE_ID:
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
