"""Оркестратор FSM (гибридная архитектура)."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from application.commands import (
    Command,
    ConfirmSkipWarning,
    Continue,
    DialogDone,
    ExplanationDone,
    PracticeEvaluated,
    RepeatCycle,
    ResumeChoice,
    ScenarioDone,
    SelectMode,
    StartSession,
    StartTraining,
    SubmitQuizAnswer,
    TheoryDone,
    UserMessage,
    WeakZonesSent,
    ZonesDone,
)
from application.effects import ClearSession, Effect, EmitMessage, PersistSession
from domain.constants import TRAINING_QUIZ_QUESTIONS
from domain.context import SessionContext
from domain.events import FSMEvent
from domain.states import FSMState, Mode
from domain.transitions import get_next_state
from domain.types import ChatMessage


@dataclass(frozen=True)
class FSMResult:
    new_state: FSMState
    new_ctx: SessionContext
    effects: tuple[Effect, ...]


_DIALOG_STATES: frozenset[FSMState] = frozenset(
    {
        FSMState.TRAINING,
        FSMState.TRAINING_QUIZ,
        FSMState.EXAMPLE,
        FSMState.PRACTICE,
        FSMState.KNOWLEDGE,
    }
)


def _reset_history_if_any(ctx: SessionContext) -> SessionContext:
    if not ctx.dialog_history:
        return ctx
    return dataclasses.replace(ctx, dialog_history=())


class FSMService:
    def handle(
        self,
        state: FSMState,
        command: Command,
        ctx: SessionContext,
    ) -> FSMResult:
        if isinstance(command, StartSession):
            return self._handle_start_session(state, ctx)
        if isinstance(command, ResumeChoice):
            return self._handle_resume_choice(state, command, ctx)
        if isinstance(command, StartTraining):
            return self._handle_start_training(state, command, ctx)
        if isinstance(command, SelectMode):
            return self._handle_select_mode(state, command, ctx)
        if isinstance(command, ConfirmSkipWarning):
            return self._handle_confirm_skip_warning(state, command, ctx)
        if isinstance(command, TheoryDone):
            return self._handle_theory_done(state, ctx)
        if isinstance(command, SubmitQuizAnswer):
            return self._handle_submit_quiz_answer(state, command, ctx)
        if isinstance(command, ExplanationDone):
            return self._handle_explanation_done(state, ctx)
        if isinstance(command, ScenarioDone):
            return self._handle_scenario_done(state, ctx)
        if isinstance(command, DialogDone):
            return self._handle_dialog_done(state, ctx)
        if isinstance(command, PracticeEvaluated):
            return self._handle_practice_evaluated(state, command, ctx)
        if isinstance(command, WeakZonesSent):
            return self._handle_weak_zones_sent(state, ctx)
        if isinstance(command, Continue):
            return self._handle_continue(state, ctx)
        if isinstance(command, ZonesDone):
            return self._handle_zones_done(state, ctx)
        if isinstance(command, RepeatCycle):
            return self._handle_repeat_cycle(state, ctx)
        if isinstance(command, UserMessage):
            return self._handle_user_message(state, command, ctx)

        raise ValueError(f"Неизвестная команда: {command!r}")

    # ------------------------------------------------------------------
    # INIT
    # ------------------------------------------------------------------

    def _handle_start_session(self, state: FSMState, ctx: SessionContext) -> FSMResult:
        if state is not FSMState.INIT:
            raise ValueError(f"StartSession допустима только в INIT, получено {state}")

        if ctx.has_active_session:
            new_state = get_next_state(state, FSMEvent.SESSION_FOUND)
            return FSMResult(new_state, ctx, (PersistSession(),))

        new_state = get_next_state(state, FSMEvent.SESSION_NOT_FOUND)
        return FSMResult(new_state, ctx, (PersistSession(),))

    # ------------------------------------------------------------------
    # RESUME_PROMPT
    # ------------------------------------------------------------------

    def _handle_resume_choice(
        self,
        state: FSMState,
        command: ResumeChoice,
        ctx: SessionContext,
    ) -> FSMResult:
        if state is not FSMState.RESUME_PROMPT:
            raise ValueError(
                f"ResumeChoice допустима только в RESUME_PROMPT, получено {state}",
            )

        if command.resume:
            if ctx.saved_state is None:
                raise ValueError("ResumeChoice(resume=True), но ctx.saved_state не задан")
            return FSMResult(ctx.saved_state, ctx, (PersistSession(),))

        new_state = get_next_state(state, FSMEvent.RESTART_CONFIRMED)
        return FSMResult(new_state, ctx, (ClearSession(), PersistSession()))

    # ------------------------------------------------------------------
    # MENU
    # ------------------------------------------------------------------

    def _handle_start_training(
        self,
        state: FSMState,
        command: StartTraining,
        ctx: SessionContext,
    ) -> FSMResult:
        if state is not FSMState.MENU:
            raise ValueError(f"StartTraining допустима только в MENU, получено {state}")

        new_state = get_next_state(state, FSMEvent.TRAINING_STARTED)
        new_ctx = dataclasses.replace(
            ctx,
            employee_name=command.employee_name or ctx.employee_name,
            product_id=command.product_id or ctx.product_id,
        )
        return FSMResult(new_state, new_ctx, (PersistSession(),))

    # ------------------------------------------------------------------
    # WELCOME
    # ------------------------------------------------------------------

    def _handle_select_mode(
        self,
        state: FSMState,
        command: SelectMode,
        ctx: SessionContext,
    ) -> FSMResult:
        if state is not FSMState.WELCOME:
            raise ValueError(f"SelectMode допустима только в WELCOME, получено {state}")

        training_done = Mode.TRAINING in ctx.completed_modes
        new_ctx = _reset_history_if_any(ctx)

        if command.mode == "training":
            new_state = get_next_state(state, FSMEvent.MODE_TRAINING)
            return FSMResult(new_state, new_ctx, (PersistSession(),))

        if command.mode == "example":
            event = FSMEvent.MODE_EXAMPLE_DIRECT if training_done else FSMEvent.MODE_EXAMPLE
            new_state = get_next_state(state, event)
            return FSMResult(new_state, new_ctx, (PersistSession(),))

        if command.mode == "practice":
            event = FSMEvent.MODE_PRACTICE_DIRECT if training_done else FSMEvent.MODE_PRACTICE
            new_state = get_next_state(state, event)
            return FSMResult(new_state, new_ctx, (PersistSession(),))

        if command.mode == "knowledge":
            if not ctx.knowledge_unlocked:
                return FSMResult(state, ctx, (EmitMessage("knowledge_locked_hint"),))
            new_state = get_next_state(state, FSMEvent.MODE_KNOWLEDGE)
            return FSMResult(new_state, new_ctx, (PersistSession(),))

        raise ValueError(f"Неизвестный режим: {command.mode!r}")

    # ------------------------------------------------------------------
    # SKIP_WARNING_1 / 2
    # ------------------------------------------------------------------

    def _handle_confirm_skip_warning(
        self,
        state: FSMState,
        command: ConfirmSkipWarning,
        ctx: SessionContext,
    ) -> FSMResult:
        if state not in (FSMState.SKIP_WARNING_1, FSMState.SKIP_WARNING_2):
            raise ValueError(
                f"ConfirmSkipWarning допустима только в SKIP_WARNING_*, получено {state}",
            )

        event = FSMEvent.WARNING_ACCEPTED if command.accept else FSMEvent.WARNING_DECLINED
        new_state = get_next_state(state, event)
        new_ctx = _reset_history_if_any(ctx) if command.accept else ctx
        return FSMResult(new_state, new_ctx, (PersistSession(),))

    # ------------------------------------------------------------------
    # TRAINING
    # ------------------------------------------------------------------

    def _handle_theory_done(self, state: FSMState, ctx: SessionContext) -> FSMResult:
        if state is not FSMState.TRAINING:
            raise ValueError(f"TheoryDone допустима только в TRAINING, получено {state}")

        new_state = get_next_state(state, FSMEvent.THEORY_DONE)
        # Этап LEARNING_CHECK — продолжение единого TRAINING-диалога:
        # dialog_history НЕ сбрасывается (сбрасываются только счётчики квиза).
        new_ctx = dataclasses.replace(
            ctx,
            quiz_question_index=0,
            last_answer_correct=None,
            quiz_target_questions=TRAINING_QUIZ_QUESTIONS,
            quiz_history=(),
        )
        return FSMResult(new_state, new_ctx, (PersistSession(),))

    def _handle_submit_quiz_answer(
        self,
        state: FSMState,
        command: SubmitQuizAnswer,
        ctx: SessionContext,
    ) -> FSMResult:
        if state is not FSMState.TRAINING_QUIZ:
            raise ValueError(
                f"SubmitQuizAnswer допустима только в TRAINING_QUIZ, получено {state}",
            )

        if not command.correct:
            new_state = get_next_state(state, FSMEvent.HAS_ERRORS)
            new_ctx = dataclasses.replace(ctx, last_answer_correct=False)
            return FSMResult(new_state, new_ctx, (PersistSession(),))

        next_index = ctx.quiz_question_index + 1
        # Целевое число вопросов — берём из контекста (мог уменьшить QuizDirector).
        # Защитный clamp: target не может быть больше технического предела.
        target = min(ctx.quiz_target_questions, TRAINING_QUIZ_QUESTIONS)
        is_last_question = next_index >= target

        if not is_last_question:
            new_ctx = dataclasses.replace(
                ctx, quiz_question_index=next_index, last_answer_correct=True
            )
            return FSMResult(state, new_ctx, (PersistSession(),))

        new_state = get_next_state(state, FSMEvent.ALL_CORRECT)
        new_ctx = dataclasses.replace(
            ctx,
            quiz_question_index=next_index,
            last_answer_correct=True,
            completed_modes=ctx.completed_modes | {Mode.TRAINING},
        )
        return FSMResult(new_state, new_ctx, (PersistSession(),))

    def _handle_explanation_done(self, state: FSMState, ctx: SessionContext) -> FSMResult:
        if state is not FSMState.TRAINING_EXPLAIN:
            raise ValueError(
                f"ExplanationDone допустима только в TRAINING_EXPLAIN, получено {state}",
            )
        new_state = get_next_state(state, FSMEvent.EXPLANATION_DONE)
        new_ctx = dataclasses.replace(ctx, last_answer_correct=None)
        return FSMResult(new_state, new_ctx, (PersistSession(),))

    # ------------------------------------------------------------------
    # EXAMPLE
    # ------------------------------------------------------------------

    def _handle_scenario_done(self, state: FSMState, ctx: SessionContext) -> FSMResult:
        if state is not FSMState.EXAMPLE:
            raise ValueError(f"ScenarioDone допустима только в EXAMPLE, получено {state}")
        new_state = get_next_state(state, FSMEvent.SCENARIO_DONE)
        new_ctx = dataclasses.replace(
            ctx,
            completed_modes=ctx.completed_modes | {Mode.EXAMPLE},
            dialog_history=(),
        )
        return FSMResult(new_state, new_ctx, (PersistSession(),))

    # ------------------------------------------------------------------
    # PRACTICE
    # ------------------------------------------------------------------

    def _handle_dialog_done(self, state: FSMState, ctx: SessionContext) -> FSMResult:
        if state is not FSMState.PRACTICE:
            raise ValueError(f"DialogDone допустима только в PRACTICE, получено {state}")
        new_state = get_next_state(state, FSMEvent.DIALOG_DONE)
        return FSMResult(new_state, ctx, (PersistSession(),))

    def _handle_practice_evaluated(
        self,
        state: FSMState,
        command: PracticeEvaluated,
        ctx: SessionContext,
    ) -> FSMResult:
        if state is not FSMState.PRACTICE_EVAL:
            raise ValueError(
                f"PracticeEvaluated допустима только в PRACTICE_EVAL, получено {state}",
            )

        if command.weak_zones:
            new_state = get_next_state(state, FSMEvent.HAS_FAILURES)
            new_ctx = dataclasses.replace(ctx, weak_zones_remaining=command.weak_zones)
            return FSMResult(new_state, new_ctx, (PersistSession(),))

        new_state = get_next_state(state, FSMEvent.ALL_ZONES_OK)
        new_ctx = dataclasses.replace(
            ctx,
            completed_modes=ctx.completed_modes | {Mode.PRACTICE},
            weak_zones_remaining=(),
        )
        return FSMResult(new_state, new_ctx, (PersistSession(),))

    def _handle_weak_zones_sent(self, state: FSMState, ctx: SessionContext) -> FSMResult:
        if state is not FSMState.PRACTICE_PARTIAL:
            raise ValueError(
                f"WeakZonesSent допустима только в PRACTICE_PARTIAL, получено {state}",
            )
        new_state = get_next_state(state, FSMEvent.WEAK_ZONES_SENT)
        new_ctx = _reset_history_if_any(ctx)
        return FSMResult(new_state, new_ctx, (PersistSession(),))

    # ------------------------------------------------------------------
    # KNOWLEDGE
    # ------------------------------------------------------------------

    def _handle_zones_done(self, state: FSMState, ctx: SessionContext) -> FSMResult:
        if state is not FSMState.KNOWLEDGE:
            raise ValueError(f"ZonesDone допустима только в KNOWLEDGE, получено {state}")
        new_state = get_next_state(state, FSMEvent.ZONES_DONE)
        new_ctx = dataclasses.replace(
            ctx,
            completed_modes=ctx.completed_modes | {Mode.KNOWLEDGE},
            weak_zones_remaining=(),
            dialog_history=(),
        )
        return FSMResult(new_state, new_ctx, (PersistSession(),))

    def _handle_repeat_cycle(self, state: FSMState, ctx: SessionContext) -> FSMResult:
        if state is not FSMState.KNOWLEDGE_DONE:
            raise ValueError(f"RepeatCycle допустима только в KNOWLEDGE_DONE, получено {state}")
        new_state = get_next_state(state, FSMEvent.REPEAT_CYCLE)
        new_ctx = dataclasses.replace(
            ctx,
            cycle_count=ctx.cycle_count + 1,
            dialog_history=(),
        )
        return FSMResult(new_state, new_ctx, (PersistSession(),))

    # ------------------------------------------------------------------
    # Continue
    # ------------------------------------------------------------------

    def _handle_continue(self, state: FSMState, ctx: SessionContext) -> FSMResult:
        if state in (
            FSMState.TRAINING_DONE,
            FSMState.EXAMPLE_DONE,
            FSMState.PRACTICE_SUCCESS,
        ):
            new_state = get_next_state(state, FSMEvent.CONTINUE)
            new_ctx = _reset_history_if_any(ctx)
            return FSMResult(new_state, new_ctx, (PersistSession(),))
        raise ValueError(
            f"Continue допустима только в TRAINING_DONE/EXAMPLE_DONE/PRACTICE_SUCCESS, "
            f"получено {state}"
        )

    # ------------------------------------------------------------------
    # UserMessage
    # ------------------------------------------------------------------

    def _handle_user_message(
        self,
        state: FSMState,
        command: UserMessage,
        ctx: SessionContext,
    ) -> FSMResult:
        if state not in _DIALOG_STATES:
            raise ValueError(
                f"UserMessage допустима только в TRAINING/TRAINING_QUIZ/"
                f"EXAMPLE/PRACTICE/KNOWLEDGE, получено {state}"
            )
        text = (command.text or "").strip()
        if not text:
            return FSMResult(state, ctx, ())

        # Этап LEARNING_CHECK (TRAINING_QUIZ) — продолжение единого
        # TRAINING-диалога: реплика пишется в общую историю.
        new_history = (*ctx.dialog_history, ChatMessage(role="user", text=text))
        new_ctx = dataclasses.replace(ctx, dialog_history=new_history)
        return FSMResult(state, new_ctx, (PersistSession(),))
