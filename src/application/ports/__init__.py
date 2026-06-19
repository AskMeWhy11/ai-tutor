"""Application ports — interfaces between application layer and infrastructure.

Implementations live in `infrastructure/`; tests use fakes from `tests/fakes/`.
"""

from application.ports.session_store import SessionSnapshot, SessionStore

__all__ = ["SessionSnapshot", "SessionStore"]
