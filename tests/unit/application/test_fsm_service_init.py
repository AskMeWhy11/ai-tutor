"""FSMService: блок INIT (StartSession)."""

from __future__ import annotations

import pytest

from application.commands import StartSession
from application.effects import PersistSession
from application.fsm_service import FSMService
from domain.context import SessionContext
from domain.states import FSMState


class TestStartSession:
    def test_active_session_goes_to_resume_prompt(self) -> None:
        service = FSMService()
        ctx = SessionContext(has_active_session=True, saved_state=FSMState.TRAINING)

        result = service.handle(FSMState.INIT, StartSession(), ctx)

        assert result.new_state is FSMState.RESUME_PROMPT
        assert result.new_ctx is ctx
        assert result.effects == (PersistSession(),)

    def test_no_active_session_goes_to_menu(self) -> None:
        service = FSMService()
        ctx = SessionContext(has_active_session=False)

        result = service.handle(FSMState.INIT, StartSession(), ctx)

        assert result.new_state is FSMState.MENU
        assert result.new_ctx is ctx
        assert result.effects == (PersistSession(),)

    def test_start_session_only_valid_in_init(self) -> None:
        service = FSMService()
        ctx = SessionContext()

        with pytest.raises(ValueError, match="StartSession допустима только в INIT"):
            service.handle(FSMState.MENU, StartSession(), ctx)
