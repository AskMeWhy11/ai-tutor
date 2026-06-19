"""SessionStore port — persistence interface for FSM sessions.

The application layer depends on this Protocol; concrete implementations
(Postgres, in-memory) live elsewhere. See ADR-007 for the design rationale.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from domain.context import SessionContext
from domain.states import FSMState


@dataclass(frozen=True)
class SessionSnapshot:
    """Immutable snapshot of a session loaded from the store.

    Returned by `SessionStore.load`. Contains everything needed to resume
    FSM execution: the current state and the full context.
    """

    state: FSMState
    ctx: SessionContext


class SessionStore(Protocol):
    """Async port for persisting and loading FSM sessions.

    Implementations must be safe to use across multiple `SessionRunner`
    instances pointing at the same backing store (i.e. `save` is upsert).
    """

    async def load(self, session_id: UUID) -> SessionSnapshot | None:
        """Return the latest snapshot for `session_id`, or None if absent."""
        ...

    async def save(
        self,
        session_id: UUID,
        state: FSMState,
        ctx: SessionContext,
    ) -> None:
        """Upsert the session: insert if missing, overwrite if present.

        Implementations must update `last_activity_at` on every save.
        """
        ...
