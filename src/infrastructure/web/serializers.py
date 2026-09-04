"""Сериализация результата FSM в DTO для HTTP-ответа."""

from __future__ import annotations

from uuid import UUID

from application.effects import (
    ClearSession,
    Effect,
    EmitHint,
    EmitMessage,
    EmitText,
    PersistSession,
    PlayAudio,
)
from application.fsm_service import FSMResult
from domain.context import SessionContext
from domain.states import FSMState
from infrastructure.web.command_mapper import available_commands_for
from infrastructure.web.schemas import ChatMessageOut, CtxOut, SessionOut


def serialize_ctx(ctx: SessionContext) -> CtxOut:
    return CtxOut(
        employee_name=ctx.employee_name,
        product_id=ctx.product_id,
        training_only=ctx.training_only,
        completed_modes=sorted(m.value for m in ctx.completed_modes),
        weak_zones_remaining=list(ctx.weak_zones_remaining),
        cycle_count=ctx.cycle_count,
        quiz_question_index=ctx.quiz_question_index,
        last_answer_correct=ctx.last_answer_correct,
        knowledge_unlocked=ctx.knowledge_unlocked,
    )


def serialize_history(ctx: SessionContext) -> list[ChatMessageOut]:
    return [ChatMessageOut(role=m.role, text=m.text) for m in ctx.dialog_history]


def serialize_effect(effect: Effect) -> dict[str, str]:
    if isinstance(effect, EmitMessage):
        return {"type": "emit_message", "key": effect.key}
    if isinstance(effect, EmitText):
        return {"type": "emit_text", "text": effect.text}
    if isinstance(effect, EmitHint):
        return {"type": "emit_hint", "text": effect.text}
    if isinstance(effect, PlayAudio):
        return {"type": "play_audio", "url": effect.url, "mime": effect.mime}
    if isinstance(effect, PersistSession):
        return {"type": "persist_session"}
    if isinstance(effect, ClearSession):
        return {"type": "clear_session"}
    return {"type": type(effect).__name__}


def serialize_session(
    session_id: UUID,
    state: FSMState,
    ctx: SessionContext,
    effects: tuple[Effect, ...],
) -> SessionOut:
    return SessionOut(
        session_id=session_id,
        state=state.value,
        ctx=serialize_ctx(ctx),
        effects=[serialize_effect(e) for e in effects],
        available_commands=available_commands_for(state),
        history=serialize_history(ctx),
    )


def serialize_result(session_id: UUID, result: FSMResult) -> SessionOut:
    return serialize_session(session_id, result.new_state, result.new_ctx, result.effects)
