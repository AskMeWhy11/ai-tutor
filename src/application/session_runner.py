"""SessionRunner — async-координатор обработки команд FSM.

В Срезе 2 все переходы между стадиями (TRAINING / EXAMPLE / PRACTICE /
KNOWLEDGE) принимает LLM через StageDirector. SessionRunner после каждой
UserMessage в режимной стадии:
  1) обновляет историю (FSMService),
  2) генерирует реплику аватара,
  3) вызывает StageDirector.decide(...) и при done=True эмитит соответствующую
     команду FSM, цепочкой авто-доводит сессию до следующего «активного»
     состояния (EXAMPLE_DONE→PRACTICE, KNOWLEDGE_DONE→EXAMPLE, ...).
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Protocol
from uuid import UUID

from application.commands import (
    Command,
    Continue,
    DialogDone,
    ExplanationDone,
    PracticeEvaluated,
    RepeatCycle,
    ScenarioDone,
    SubmitQuizAnswer,
    TheoryDone,
    UserMessage,
    WeakZonesSent,
    ZonesDone,
)
from application.effects import (
    Effect,
    EmitHint,
    EmitMessage,
    EmitText,
    PersistSession,
    PlayAudio,
)
from application.fsm_service import FSMResult, FSMService
from application.ports.answer_checker import AnswerChecker
from application.ports.avatar import AvatarClient
from application.ports.practice_evaluator import PracticeEvaluator
from application.ports.quiz_director import QuizDirector
from application.ports.session_store import SessionStore
from application.ports.stage_director import StageDecision, StageDirector
from application.ports.tts_client import TTSClient
from domain.context import SessionContext
from domain.states import FSMState
from domain.types import ZONE_ORDER, ChatMessage
from infrastructure.content.case_loader import resolve_case_id
from infrastructure.content.cc_novichok import EXAMPLE_DIALOGUE
from infrastructure.content.registry import DEFAULT_CASE_ID

__all__ = ["AudioCachePort", "SessionRunner"]

logger = logging.getLogger(__name__)

_MESSAGE_KEYS_RU: dict[str, str] = {
    "knowledge_locked_hint": (
        "Раздел «Знания» станет доступен после прохождения «Практики» — "
        "он прокачивает западающие зоны."
    ),
}

_HISTORY_STATES: frozenset[FSMState] = frozenset(
    {
        FSMState.TRAINING,
        FSMState.EXAMPLE,
        FSMState.PRACTICE,
        FSMState.KNOWLEDGE,
    }
)

# Стадии, где судья решает завершение через StageDirector.
_DIRECTED_STAGES: frozenset[FSMState] = frozenset(
    {
        FSMState.TRAINING,
        FSMState.EXAMPLE,
        FSMState.PRACTICE,
        FSMState.KNOWLEDGE,
    }
)


class AudioCachePort(Protocol):
    async def put(self, audio: bytes, ext: str) -> str: ...


class SessionRunner:
    def __init__(
        self,
        fsm: FSMService,
        store: SessionStore,
        avatar: AvatarClient | None = None,
        tts: TTSClient | None = None,
        audio_cache: AudioCachePort | None = None,
        answer_checker: AnswerChecker | None = None,
        practice_evaluator: PracticeEvaluator | None = None,
        quiz_director: QuizDirector | None = None,
        stage_director: StageDirector | None = None,
    ) -> None:
        self._fsm = fsm
        self._store = store
        self._avatar = avatar
        self._tts = tts
        self._audio_cache = audio_cache
        self._answer_checker = answer_checker
        self._practice_evaluator = practice_evaluator
        self._quiz_director = quiz_director
        self._stage_director = stage_director

    # ------------------------------------------------------------------
    # Точка входа
    # ------------------------------------------------------------------

    async def dispatch(self, session_id: UUID, command: Command) -> FSMResult:
        snapshot = await self._store.load(session_id)
        if snapshot is None:
            state: FSMState = FSMState.INIT
            ctx = SessionContext()
        else:
            state = snapshot.state
            ctx = snapshot.ctx

        # TRAINING_QUIZ ведёт QuizDirector — это отдельный путь.
        if (
            state is FSMState.TRAINING_QUIZ
            and isinstance(command, UserMessage)
            and self._quiz_director is not None
        ):
            return await self._run_quiz_turn(session_id, ctx, command.text)

        # 1) Базовый handle.
        result = self._fsm.handle(state, command, ctx)
        if any(isinstance(e, PersistSession) for e in result.effects):
            await self._store.save(session_id, result.new_state, result.new_ctx)

        cur_state = result.new_state
        cur_ctx = result.new_ctx

        # 1a) Если попали в PRACTICE_EVAL прямой командой (DialogDone) —
        # сразу зовём PracticeEvaluator и едем дальше по цепочке.
        eval_chain_effects: tuple[Effect, ...] = ()
        if (
            cur_state is FSMState.PRACTICE_EVAL
            and isinstance(command, DialogDone)
            and self._practice_evaluator is not None
        ):
            cur_state, cur_ctx, eval_chain_effects = await self._run_practice_eval_chain(
                session_id, cur_ctx
            )

        # 2) Реплика аватара.
        avatar_effects, ctx_after_avatar = await self._build_avatar_effects(cur_state, cur_ctx)
        if ctx_after_avatar is not cur_ctx:
            await self._store.save(session_id, cur_state, ctx_after_avatar)
        cur_ctx = ctx_after_avatar

        # 3) StageDirector: решает, не пора ли закрыть стадию.
        director_effects: tuple[Effect, ...] = ()
        if (
            isinstance(command, UserMessage)
            and cur_state in _DIRECTED_STAGES
            and self._stage_director is not None
        ):
            cur_state, cur_ctx, director_effects = await self._run_stage_director_chain(
                session_id, state_before=state, state=cur_state, ctx=cur_ctx
            )

        # 4) Сборка эффектов.
        domain_effects = tuple(e for e in result.effects if not isinstance(e, PersistSession))
        resolved: list[Effect] = []
        for e in domain_effects:
            if isinstance(e, EmitMessage):
                text = _MESSAGE_KEYS_RU.get(e.key)
                if text:
                    resolved.append(EmitText(text=text))
                else:
                    logger.warning("EmitMessage с неизвестным ключом: %s", e.key)
            else:
                resolved.append(e)
        domain_effects = tuple(resolved)

        merged: tuple[Effect, ...] = (
            PersistSession(),
            *eval_chain_effects,
            *avatar_effects,
            *director_effects,
            *domain_effects,
        )
        return FSMResult(new_state=cur_state, new_ctx=cur_ctx, effects=merged)

    async def _run_practice_eval_chain(
        self,
        session_id: UUID,
        ctx: SessionContext,
    ) -> tuple[FSMState, SessionContext, tuple[Effect, ...]]:
        """PRACTICE_EVAL → PracticeEvaluator → авто-цепочка до KNOWLEDGE/FINISH."""
        assert self._practice_evaluator is not None
        try:
            weak = await self._practice_evaluator.evaluate(
                ctx.dialog_history, case_id=ctx.product_id or None
            )
        except Exception:
            logger.exception("practice_evaluator failed")
            return FSMState.PRACTICE_EVAL, ctx, ()

        cur_state, cur_ctx = await self._apply_cmd(
            session_id,
            FSMState.PRACTICE_EVAL,
            ctx,
            PracticeEvaluated(weak_zones=weak),
        )
        cur_state, cur_ctx, chain = await self._advance_chain(session_id, cur_state, cur_ctx)
        return cur_state, cur_ctx, tuple(chain)

    # ------------------------------------------------------------------
    # StageDirector + цепочка авто-команд
    # ------------------------------------------------------------------

    async def _run_stage_director_chain(
        self,
        session_id: UUID,
        *,
        state_before: FSMState,
        state: FSMState,
        ctx: SessionContext,
    ) -> tuple[FSMState, SessionContext, tuple[Effect, ...]]:
        """Спросить StageDirector. Если done — авто-эмитим команды до
        следующего «активного» состояния (EXAMPLE/PRACTICE/KNOWLEDGE/QUIZ/FINISH).
        """
        assert self._stage_director is not None

        try:
            decision = await self._stage_director.decide(state=state, ctx=ctx)
        except Exception:
            logger.exception("stage_director.decide failed")
            return state, ctx, ()

        if not decision.done:
            return state, ctx, ()

        logger.info(
            "stage_director: state=%s done outcome=%s reason=%s",
            state,
            decision.outcome,
            decision.reason,
        )

        effects: list[Effect] = []
        cur_state = state
        cur_ctx = ctx

        # 1) Эмитим первичную «закрывающую» команду стадии.
        first_cmd, special = self._build_close_command(state, decision)
        if first_cmd is None and special is None:
            return cur_state, cur_ctx, ()

        if special == "practice_refused_eval":
            # PRACTICE refused → DialogDone + PracticeEvaluator (LLM сама
            # решит, какие зоны западают по куску диалога).
            cur_state, cur_ctx = await self._apply_cmd(session_id, cur_state, cur_ctx, DialogDone())
            weak = await self._eval_practice(cur_ctx)
            cur_state, cur_ctx = await self._apply_cmd(
                session_id, cur_state, cur_ctx, PracticeEvaluated(weak_zones=weak)
            )
        else:
            assert first_cmd is not None
            # Для PRACTICE accepted сначала DialogDone, потом нормальный eval.
            if state is FSMState.PRACTICE:
                cur_state, cur_ctx = await self._apply_cmd(
                    session_id, cur_state, cur_ctx, DialogDone()
                )
                weak = await self._eval_practice(cur_ctx)
                cur_state, cur_ctx = await self._apply_cmd(
                    session_id, cur_state, cur_ctx, PracticeEvaluated(weak_zones=weak)
                )
            else:
                cur_state, cur_ctx = await self._apply_cmd(
                    session_id, cur_state, cur_ctx, first_cmd
                )

        # 2) Авто-довод до следующего «активного» состояния.
        cur_state, cur_ctx, chain_effects = await self._advance_chain(
            session_id, cur_state, cur_ctx
        )
        effects.extend(chain_effects)

        return cur_state, cur_ctx, tuple(effects)

    @staticmethod
    def _build_close_command(
        state: FSMState, decision: StageDecision
    ) -> tuple[Command | None, str | None]:
        """Команда, закрывающая стадию по решению StageDirector.

        Возвращает (cmd, special). special — маркер нестандартной обработки.
        """
        if state is FSMState.TRAINING:
            if decision.outcome == "training_understood":
                return TheoryDone(), None
            return None, None

        if state is FSMState.EXAMPLE:
            if decision.outcome in ("example_accepted", "example_refused_3x"):
                return ScenarioDone(), None
            return None, None

        if state is FSMState.PRACTICE:
            if decision.outcome == "practice_accepted":
                return DialogDone(), None
            if decision.outcome == "practice_refused":
                # Вариант B: всё равно идём через PRACTICE_EVAL.
                return None, "practice_refused_eval"
            return None, None

        if state is FSMState.KNOWLEDGE:
            if decision.outcome == "knowledge_understood":
                return ZonesDone(), None
            return None, None

        return None, None

    async def _advance_chain(
        self,
        session_id: UUID,
        state: FSMState,
        ctx: SessionContext,
    ) -> tuple[FSMState, SessionContext, list[Effect]]:
        """Автоматически проходит «технические» состояния без участия пользователя.

        Маршруты:
          TRAINING_DONE   → CONTINUE → EXAMPLE
          EXAMPLE_DONE    → CONTINUE → PRACTICE
          PRACTICE_PARTIAL→ WeakZonesSent → KNOWLEDGE
          KNOWLEDGE_DONE  → RepeatCycle → EXAMPLE
          PRACTICE_SUCCESS→ CONTINUE → FINISH

        На каждом шаге: эмитим реплику аватара (если есть), затем шлём команду.
        """
        effects: list[Effect] = []
        cur_state = state
        cur_ctx = ctx
        # Защита от бесконечного цикла.
        max_steps = 6
        for _ in range(max_steps):
            # Сначала озвучим состояние, если у него есть «статичная» реплика.
            avatar_effects, new_ctx = await self._build_avatar_effects(cur_state, cur_ctx)
            if new_ctx is not cur_ctx:
                await self._store.save(session_id, cur_state, new_ctx)
                cur_ctx = new_ctx
            effects.extend(avatar_effects)

            auto_cmd = self._auto_advance_command(cur_state)
            if auto_cmd is None:
                break

            cur_state, cur_ctx = await self._apply_cmd(session_id, cur_state, cur_ctx, auto_cmd)

        return cur_state, cur_ctx, effects

    @staticmethod
    def _auto_advance_command(state: FSMState) -> Command | None:
        if state is FSMState.TRAINING_DONE:
            return Continue()
        if state is FSMState.EXAMPLE_DONE:
            return Continue()
        if state is FSMState.PRACTICE_PARTIAL:
            return WeakZonesSent()
        if state is FSMState.KNOWLEDGE_DONE:
            return RepeatCycle()
        if state is FSMState.PRACTICE_SUCCESS:
            return Continue()
        return None

    async def _apply_cmd(
        self,
        session_id: UUID,
        state: FSMState,
        ctx: SessionContext,
        cmd: Command,
    ) -> tuple[FSMState, SessionContext]:
        try:
            res = self._fsm.handle(state, cmd, ctx)
        except Exception:
            logger.exception("auto-command %s failed in state=%s", type(cmd).__name__, state)
            return state, ctx
        if any(isinstance(e, PersistSession) for e in res.effects):
            await self._store.save(session_id, res.new_state, res.new_ctx)
        return res.new_state, res.new_ctx

    async def _eval_practice(self, ctx: SessionContext) -> tuple[str, ...]:
        if self._practice_evaluator is None:
            return ZONE_ORDER  # без оценщика считаем все зоны западающими
        try:
            return await self._practice_evaluator.evaluate(
                ctx.dialog_history, case_id=ctx.product_id or None
            )
        except Exception:
            logger.exception("practice_evaluator failed")
            return ZONE_ORDER

    # ------------------------------------------------------------------
    # TRAINING_QUIZ через QuizDirector (без изменений)
    # ------------------------------------------------------------------

    async def _run_quiz_turn(
        self,
        session_id: UUID,
        ctx: SessionContext,
        user_text: str,
    ) -> FSMResult:
        assert self._quiz_director is not None

        text = (user_text or "").strip()
        if not text:
            return FSMResult(FSMState.TRAINING_QUIZ, ctx, ())

        try:
            turn = await self._quiz_director.next_turn(ctx, text)
        except Exception:
            logger.exception("quiz_director.next_turn failed")
            return FSMResult(FSMState.TRAINING_QUIZ, ctx, ())

        # Ведём историю квиза: ответ сотрудника + последующие реплики
        # аватара (разъяснение/следующий вопрос). Применяем к final_ctx
        # в самом конце, чтобы модель на следующем ходу видела весь ход.
        quiz_msgs: list[ChatMessage] = [ChatMessage(role="user", text=text)]

        effects: list[Effect] = [PersistSession()]
        final_state: FSMState = FSMState.TRAINING_QUIZ
        final_ctx: SessionContext = ctx

        if turn.verdict == "correct":
            ctx_for_fsm = ctx
            if turn.done:
                ctx_for_fsm = dataclasses.replace(
                    ctx, quiz_target_questions=ctx.quiz_question_index + 1
                )
            result = self._fsm.handle(
                FSMState.TRAINING_QUIZ, SubmitQuizAnswer(correct=True), ctx_for_fsm
            )
            await self._store.save(session_id, result.new_state, result.new_ctx)
            final_state = result.new_state
            final_ctx = result.new_ctx

            if final_state is FSMState.TRAINING_QUIZ and turn.next_question:
                effects.extend(await self._reply_effects(turn.next_question))
                quiz_msgs.append(ChatMessage(role="assistant", text=turn.next_question))

        elif turn.verdict == "incorrect":
            r1 = self._fsm.handle(FSMState.TRAINING_QUIZ, SubmitQuizAnswer(correct=False), ctx)
            await self._store.save(session_id, r1.new_state, r1.new_ctx)
            r2 = self._fsm.handle(FSMState.TRAINING_EXPLAIN, ExplanationDone(), r1.new_ctx)
            await self._store.save(session_id, r2.new_state, r2.new_ctx)
            final_state = r2.new_state
            final_ctx = r2.new_ctx

            if turn.explanation:
                effects.extend(await self._reply_effects(turn.explanation))
                quiz_msgs.append(ChatMessage(role="assistant", text=turn.explanation))
            if turn.next_question:
                effects.extend(await self._reply_effects(turn.next_question))
                quiz_msgs.append(ChatMessage(role="assistant", text=turn.next_question))
        else:
            if turn.next_question:
                effects.extend(await self._reply_effects(turn.next_question))
                quiz_msgs.append(ChatMessage(role="assistant", text=turn.next_question))

        # Дописываем ход квиза в историю (если квиз ещё идёт).
        if final_state in (FSMState.TRAINING_QUIZ, FSMState.TRAINING_EXPLAIN):
            merged = (*final_ctx.quiz_history, *quiz_msgs)
            final_ctx = dataclasses.replace(final_ctx, quiz_history=merged)
            await self._store.save(session_id, final_state, final_ctx)

        # Если квиз закрыт — авто-проходим TRAINING_DONE → EXAMPLE.
        # _advance_chain сам эмитит реплику TRAINING_DONE первым шагом,
        # поэтому отдельный _build_avatar_effects здесь НЕ нужен — иначе
        # реплика «Отлично, теоретическую часть прошли…» уходит дважды.
        if final_state is FSMState.TRAINING_DONE:
            final_state, final_ctx, chain = await self._advance_chain(
                session_id, final_state, final_ctx
            )
            effects.extend(chain)

        return FSMResult(new_state=final_state, new_ctx=final_ctx, effects=tuple(effects))

    async def _reply_effects(self, text: str) -> list[Effect]:
        out: list[Effect] = [EmitText(text=text)]
        if self._tts is not None and self._audio_cache is not None:
            try:
                audio = await self._tts.synthesize(text)
            except Exception:
                logger.exception("tts.synthesize failed")
                audio = None
            if audio:
                key = await self._audio_cache.put(audio, self._tts.extension)
                out.append(PlayAudio(url=f"/api/audio/{key}", mime=self._tts.mime))
        return out

    # ------------------------------------------------------------------
    # Аватар
    # ------------------------------------------------------------------

    async def _build_avatar_effects(
        self,
        state: FSMState,
        ctx: SessionContext,
    ) -> tuple[tuple[Effect, ...], SessionContext]:
        # TRAINING_QUIZ: kickoff ведёт QuizDirector.
        if state is FSMState.TRAINING_QUIZ:
            if self._quiz_director is None:
                return (), ctx
            if ctx.quiz_question_index != 0 or ctx.last_answer_correct is not None:
                return (), ctx
            try:
                turn = await self._quiz_director.next_turn(ctx, None)
            except Exception:
                logger.exception("quiz_director.next_turn (kickoff) failed")
                return (), ctx
            if not turn.next_question:
                return (), ctx
            # Первый вопрос кладём в историю квиза, чтобы модель на
            # следующем ходу видела, на что отвечает сотрудник.
            ctx = dataclasses.replace(
                ctx,
                quiz_history=(
                    *ctx.quiz_history,
                    ChatMessage(role="assistant", text=turn.next_question),
                ),
            )
            effects = await self._reply_effects(turn.next_question)
            return tuple(effects), ctx

        if self._avatar is None:
            return (), ctx
        try:
            text = await self._avatar.next_message(state, ctx)
        except Exception:
            logger.exception("avatar.next_message failed for state=%s", state)
            return (), ctx
        if not text or not text.strip():
            return (), ctx

        avatar_fx: list[Effect] = [EmitText(text=text)]

        if self._tts is not None and self._audio_cache is not None:
            try:
                audio = await self._tts.synthesize(text)
            except Exception:
                logger.exception("tts.synthesize failed")
                audio = None
            if audio:
                key = await self._audio_cache.put(audio, self._tts.extension)
                avatar_fx.append(PlayAudio(url=f"/api/audio/{key}", mime=self._tts.mime))

        hint = self._build_hint(state, ctx)
        if hint is not None:
            avatar_fx.append(hint)

        new_ctx = ctx
        if state in _HISTORY_STATES:
            new_history = (
                *ctx.dialog_history,
                ChatMessage(role="assistant", text=text),
            )
            new_ctx = dataclasses.replace(ctx, dialog_history=new_history)

        return tuple(avatar_fx), new_ctx

    @staticmethod
    def _build_hint(state: FSMState, ctx: SessionContext) -> EmitHint | None:
        if state is not FSMState.EXAMPLE:
            return None
        # EXAMPLE_DIALOGUE (и его rationale-подсказки) — контент cc_novichok.
        # Для техник продаж подсказку не показываем.
        if resolve_case_id(ctx.product_id) != DEFAULT_CASE_ID:
            return None
        idx = ctx.cycle_count % len(ZONE_ORDER)
        zone = ZONE_ORDER[idx]
        turn = EXAMPLE_DIALOGUE.get(zone)
        if turn is None or not turn.rationale.strip():
            return None
        return EmitHint(text=turn.rationale)
