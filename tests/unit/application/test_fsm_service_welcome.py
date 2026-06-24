"""FSMService: блок WELCOME (SelectMode) + SKIP_WARNING (ConfirmSkipWarning).

Это ядро гибридной архитектуры: оркестратор смотрит ctx.completed_modes
и ctx.knowledge_unlocked, чтобы выбрать одно из нескольких событий FSM
для одной и той же команды.
"""

from __future__ import annotations

import pytest

from application.commands import ConfirmSkipWarning, SelectMode
from application.effects import EmitMessage, PersistSession
from application.fsm_service import FSMService
from domain.context import SessionContext
from domain.states import FSMState, Mode


class TestSelectModeTraining:
    def test_training_goes_to_training_state(self) -> None:
        service = FSMService()
        ctx = SessionContext()

        result = service.handle(FSMState.WELCOME, SelectMode("training"), ctx)

        assert result.new_state is FSMState.TRAINING
        assert result.new_ctx is ctx
        assert result.effects == (PersistSession(),)


class TestSelectModeExample:
    def test_example_without_training_goes_to_skip_warning(self) -> None:
        service = FSMService()
        ctx = SessionContext(completed_modes=frozenset())

        result = service.handle(FSMState.WELCOME, SelectMode("example"), ctx)

        assert result.new_state is FSMState.SKIP_WARNING_1
        assert result.new_ctx is ctx
        assert result.effects == (PersistSession(),)

    def test_example_with_training_goes_directly(self) -> None:
        service = FSMService()
        ctx = SessionContext(completed_modes=frozenset({Mode.TRAINING}))

        result = service.handle(FSMState.WELCOME, SelectMode("example"), ctx)

        assert result.new_state is FSMState.EXAMPLE
        assert result.new_ctx is ctx
        assert result.effects == (PersistSession(),)


class TestSelectModePractice:
    def test_practice_without_training_goes_to_skip_warning(self) -> None:
        service = FSMService()
        ctx = SessionContext(completed_modes=frozenset())

        result = service.handle(FSMState.WELCOME, SelectMode("practice"), ctx)

        assert result.new_state is FSMState.SKIP_WARNING_2
        assert result.new_ctx is ctx
        assert result.effects == (PersistSession(),)

    def test_practice_with_training_goes_directly(self) -> None:
        service = FSMService()
        ctx = SessionContext(completed_modes=frozenset({Mode.TRAINING}))

        result = service.handle(FSMState.WELCOME, SelectMode("practice"), ctx)

        assert result.new_state is FSMState.PRACTICE
        assert result.new_ctx is ctx
        assert result.effects == (PersistSession(),)


class TestSelectModeKnowledge:
    def test_knowledge_locked_emits_hint_and_keeps_state(self) -> None:
        """KNOWLEDGE недоступен (PRACTICE не пройдена): подсказка, состояние WELCOME."""
        service = FSMService()
        ctx = SessionContext(completed_modes=frozenset())

        result = service.handle(FSMState.WELCOME, SelectMode("knowledge"), ctx)

        assert result.new_state is FSMState.WELCOME
        assert result.new_ctx is ctx
        assert result.effects == (EmitMessage("knowledge_locked_hint"),)

    def test_knowledge_locked_when_practice_done_but_no_weak_zones(self) -> None:
        """PRACTICE пройдена, но weak_zones пуст — KNOWLEDGE не нужен."""
        service = FSMService()
        ctx = SessionContext(
            completed_modes=frozenset({Mode.PRACTICE}),
            weak_zones_remaining=(),
        )

        result = service.handle(FSMState.WELCOME, SelectMode("knowledge"), ctx)

        assert result.new_state is FSMState.WELCOME
        assert result.new_ctx is ctx
        assert result.effects == (EmitMessage("knowledge_locked_hint"),)

    def test_knowledge_unlocked_goes_to_knowledge(self) -> None:
        service = FSMService()
        ctx = SessionContext(
            completed_modes=frozenset({Mode.PRACTICE}),
            weak_zones_remaining=("greeting", "needs_analysis"),
        )

        result = service.handle(FSMState.WELCOME, SelectMode("knowledge"), ctx)

        assert result.new_state is FSMState.KNOWLEDGE
        assert result.new_ctx is ctx
        assert result.effects == (PersistSession(),)


class TestSelectModeValidation:
    def test_select_mode_only_valid_in_welcome(self) -> None:
        service = FSMService()
        ctx = SessionContext()

        with pytest.raises(ValueError, match="SelectMode допустима только в WELCOME"):
            service.handle(FSMState.MENU, SelectMode("training"), ctx)


class TestConfirmSkipWarning:
    def test_skip_warning_1_accepted_goes_to_example(self) -> None:
        service = FSMService()
        ctx = SessionContext()

        result = service.handle(
            FSMState.SKIP_WARNING_1,
            ConfirmSkipWarning(accept=True),
            ctx,
        )

        assert result.new_state is FSMState.EXAMPLE
        assert result.new_ctx is ctx
        assert result.effects == (PersistSession(),)

    def test_skip_warning_2_accepted_goes_to_practice(self) -> None:
        service = FSMService()
        ctx = SessionContext()

        result = service.handle(
            FSMState.SKIP_WARNING_2,
            ConfirmSkipWarning(accept=True),
            ctx,
        )

        assert result.new_state is FSMState.PRACTICE
        assert result.new_ctx is ctx
        assert result.effects == (PersistSession(),)

    def test_skip_warning_1_declined_returns_to_welcome(self) -> None:
        service = FSMService()
        ctx = SessionContext()

        result = service.handle(
            FSMState.SKIP_WARNING_1,
            ConfirmSkipWarning(accept=False),
            ctx,
        )

        assert result.new_state is FSMState.WELCOME
        assert result.new_ctx is ctx
        assert result.effects == (PersistSession(),)

    def test_skip_warning_2_declined_returns_to_welcome(self) -> None:
        service = FSMService()
        ctx = SessionContext()

        result = service.handle(
            FSMState.SKIP_WARNING_2,
            ConfirmSkipWarning(accept=False),
            ctx,
        )

        assert result.new_state is FSMState.WELCOME
        assert result.new_ctx is ctx
        assert result.effects == (PersistSession(),)

    def test_confirm_skip_warning_invalid_state(self) -> None:
        service = FSMService()
        ctx = SessionContext()

        with pytest.raises(ValueError, match="SKIP_WARNING_"):
            service.handle(FSMState.WELCOME, ConfirmSkipWarning(accept=True), ctx)
