"""In-memory SessionStore для разработки и Среза 2.

Один процесс, без конкуренции. Заменяется PostgresSessionStore позже.
"""

from __future__ import annotations

from uuid import UUID

from application.ports.session_store import SessionSnapshot, SessionStore
from domain.context import SessionContext
from domain.states import FSMState

__all__ = ["InMemorySessionStore"]


class InMemorySessionStore(SessionStore):
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
