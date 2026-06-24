"""FSMService: блок MENU (StartTraining)."""

from __future__ import annotations

import dataclasses

import pytest

from application.commands import StartTraining
from application.effects import PersistSession
from application.fsm_service import FSMService
from domain.context import SessionContext
from domain.states import FSMState


class TestStartTraining:
    def test_menu_to_welcome(self) -> None:
        service = FSMService()
        # Используем команду без значимых полей: дефолт product_id="cc_novichok"
        # должен попасть в ctx, поэтому сравниваем по полям, а не по identity.
        ctx = SessionContext(product_id="cc_novichok")

        result = service.handle(FSMState.MENU, StartTraining(), ctx)

        assert result.new_state is FSMState.WELCOME
        assert result.new_ctx == ctx
        assert result.effects == (PersistSession(),)

    def test_writes_employee_and_product_to_ctx(self) -> None:
        service = FSMService()
        ctx = SessionContext()

        result = service.handle(
            FSMState.MENU,
            StartTraining(employee_name="Анна", product_id="kasko"),
            ctx,
        )

        assert result.new_ctx.employee_name == "Анна"
        assert result.new_ctx.product_id == "kasko"

    def test_empty_fields_do_not_overwrite_existing(self) -> None:
        service = FSMService()
        ctx = SessionContext(employee_name="Анна", product_id="kasko")

        # StartTraining с пустыми полями нереалистична (default product_id="cc_novichok"),
        # но проверяем семантику явно.
        cmd = dataclasses.replace(StartTraining(), employee_name="", product_id="")
        result = service.handle(FSMState.MENU, cmd, ctx)

        assert result.new_ctx.employee_name == "Анна"
        assert result.new_ctx.product_id == "kasko"

    def test_start_training_only_valid_in_menu(self) -> None:
        service = FSMService()
        ctx = SessionContext()

        with pytest.raises(ValueError, match="StartTraining допустима только в MENU"):
            service.handle(FSMState.WELCOME, StartTraining(), ctx)
