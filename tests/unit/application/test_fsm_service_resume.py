"""FSMService: блок RESUME_PROMPT (ResumeChoice)."""

from __future__ import annotations

import pytest

from application.commands import ResumeChoice
from application.effects import ClearSession, PersistSession
from application.fsm_service import FSMService
from domain.context import SessionContext
from domain.states import FSMState


class TestResumeChoice:
    def test_resume_true_goes_to_saved_state(self) -> None:
        service = FSMService()
        ctx = SessionContext(has_active_session=True, saved_state=FSMState.TRAINING_QUIZ)

        result = service.handle(
            FSMState.RESUME_PROMPT,
            ResumeChoice(resume=True),
            ctx,
        )

        assert result.new_state is FSMState.TRAINING_QUIZ
        assert result.new_ctx is ctx
        assert result.effects == (PersistSession(),)

    def test_resume_true_can_restore_late_stage(self) -> None:
        service = FSMService()
        ctx = SessionContext(has_active_session=True, saved_state=FSMState.PRACTICE_PARTIAL)

        result = service.handle(
            FSMState.RESUME_PROMPT,
            ResumeChoice(resume=True),
            ctx,
        )

        assert result.new_state is FSMState.PRACTICE_PARTIAL
        assert result.new_ctx is ctx

    def test_resume_true_without_saved_state_raises(self) -> None:
        service = FSMService()
        ctx = SessionContext(has_active_session=True, saved_state=None)

        with pytest.raises(ValueError, match="saved_state не задан"):
            service.handle(
                FSMState.RESUME_PROMPT,
                ResumeChoice(resume=True),
                ctx,
            )

    def test_restart_goes_to_menu_and_clears_session(self) -> None:
        service = FSMService()
        ctx = SessionContext(has_active_session=True, saved_state=FSMState.TRAINING)

        result = service.handle(
            FSMState.RESUME_PROMPT,
            ResumeChoice(resume=False),
            ctx,
        )

        assert result.new_state is FSMState.MENU
        assert result.new_ctx is ctx
        assert result.effects == (ClearSession(), PersistSession())

    def test_resume_choice_only_valid_in_resume_prompt(self) -> None:
        service = FSMService()
        ctx = SessionContext()

        with pytest.raises(ValueError, match="ResumeChoice допустима только в RESUME_PROMPT"):
            service.handle(FSMState.MENU, ResumeChoice(resume=True), ctx)
