"""In-memory implementation of SessionStore for unit tests.

Not used in production. SessionRunner unit tests (Commit 8) and
Protocol-conformance tests (this commit) depend on this fake.
"""

from __future__ import annotations

from uuid import UUID

from application.ports.session_store import SessionSnapshot, SessionStore
from domain.context import SessionContext
from domain.states import FSMState

__all__ = ["InMemorySessionStore"]


class InMemorySessionStore(SessionStore):
    """Dict-backed SessionStore. Single-process, no concurrency guarantees.

    Suitable for unit tests only. Production uses PostgresSessionStore
    (Commit 7).
    """

    def __init__(self) -> None:
        self._snapshots: dict[UUID, SessionSnapshot] = {}

    async def load(self, session_id: UUID) -> SessionSnapshot | None:
        return self._snapshots.get(session_id)

    async def save(
        self,
        session_id: UUID,
        state: FSMState,
        ctx: SessionContext,
    ) -> None:
        self._snapshots[session_id] = SessionSnapshot(state=state, ctx=ctx)
