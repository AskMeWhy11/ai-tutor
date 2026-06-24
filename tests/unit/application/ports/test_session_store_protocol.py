"""Protocol-conformance tests for SessionStore.

These tests pin the contract: any implementation (in-memory, Postgres,
future ones) must satisfy the same behaviour. The Postgres integration
test suite (Commit 7) reuses the same scenarios against a real DB.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from uuid import uuid4

import pytest

from application.ports.session_store import SessionSnapshot, SessionStore
from domain.context import SessionContext
from domain.states import FSMState, Mode
from tests.fakes.in_memory_session_store import InMemorySessionStore


@pytest.fixture
def store() -> SessionStore:
    return InMemorySessionStore()


@pytest.fixture
def session_id():
    return uuid4()


@pytest.fixture
def initial_ctx() -> SessionContext:
    return SessionContext()


class TestSessionStoreContract:
    async def test_load_missing_returns_none(self, store, session_id):
        result = await store.load(session_id)
        assert result is None

    async def test_save_then_load_returns_snapshot(self, store, session_id, initial_ctx):
        await store.save(session_id, FSMState.MENU, initial_ctx)

        snapshot = await store.load(session_id)

        assert snapshot is not None
        assert snapshot.state == FSMState.MENU
        assert snapshot.ctx == initial_ctx

    async def test_save_overwrites_existing_session(self, store, session_id, initial_ctx):
        await store.save(session_id, FSMState.MENU, initial_ctx)
        await store.save(session_id, FSMState.WELCOME, initial_ctx)

        snapshot = await store.load(session_id)
        assert snapshot is not None
        assert snapshot.state == FSMState.WELCOME

    async def test_distinct_sessions_are_isolated(self, store, initial_ctx):
        sid_a = uuid4()
        sid_b = uuid4()

        await store.save(sid_a, FSMState.MENU, initial_ctx)
        await store.save(sid_b, FSMState.WELCOME, initial_ctx)

        snap_a = await store.load(sid_a)
        snap_b = await store.load(sid_b)

        assert snap_a is not None and snap_a.state == FSMState.MENU
        assert snap_b is not None and snap_b.state == FSMState.WELCOME

    async def test_snapshot_is_frozen(self):
        ctx = SessionContext()
        snapshot = SessionSnapshot(state=FSMState.MENU, ctx=ctx)

        with pytest.raises(FrozenInstanceError):
            snapshot.state = FSMState.WELCOME  # type: ignore[misc]

    async def test_ctx_with_complex_fields_roundtrips(self, store, session_id):
        """Сложные immutable-поля (frozenset, tuple, optional enum) должны
        переживать save→load без потери типа и значения.

        Этот тест — страховка от будущей Postgres-реализации (Commit 7):
        JSON-сериализация легко превращает frozenset в list, а Enum
        в строку. Контракт обязывает имплементацию сохранять типы.
        """
        ctx = SessionContext(
            has_active_session=True,
            employee_name="Иванов",
            product_id="vklad-premium",
            completed_modes=frozenset({Mode.TRAINING, Mode.EXAMPLE}),
            weak_zones_remaining=("zone-a", "zone-b"),
            cycle_count=2,
            quiz_question_index=3,
            last_answer_correct=True,
            saved_state=FSMState.WELCOME,
        )

        await store.save(session_id, FSMState.MENU, ctx)
        snapshot = await store.load(session_id)

        assert snapshot is not None
        assert snapshot.ctx == ctx
        # Явные проверки типов: == для frozenset/tuple проходит и для
        # list/set, поэтому страхуемся isinstance.
        assert isinstance(snapshot.ctx.completed_modes, frozenset)
        assert isinstance(snapshot.ctx.weak_zones_remaining, tuple)
        assert snapshot.ctx.saved_state is FSMState.WELCOME
