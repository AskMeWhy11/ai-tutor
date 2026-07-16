"""StubAvatar не должен подмешивать контент cc_novichok в другие кейсы.

Регресс: при падении GigaChat в диалог про технику ХПВ прилетал текст
TRAINING_BLOCKS[2] про «СберКарту 120 дней».
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from domain.context import SessionContext
from domain.states import FSMState
from domain.types import ChatMessage
from infrastructure.content.case_loader import invalidate_case_cache
from infrastructure.llm.stub_avatar import StubAvatar, _theory_blocks

_TECHNIQUES = ("xpv", "spin", "pusk", "aida", "storytelling")

# Маркеры курированного контента кредитной карты.
_CC_MARKERS = ("СберКарта 120 дней", "ФИКС", "запасной кошелёк")


def setup_function() -> None:
    invalidate_case_cache()
    _theory_blocks.cache_clear()


def _history(user_turns: int) -> tuple[ChatMessage, ...]:
    out: list[ChatMessage] = []
    for _ in range(user_turns):
        out.append(ChatMessage(role="assistant", text="..."))
        out.append(ChatMessage(role="user", text="ок"))
    return tuple(out)


@pytest.mark.asyncio
@pytest.mark.parametrize("case_id", _TECHNIQUES)
@pytest.mark.parametrize("turns", [0, 1, 2, 3])
async def test_training_stub_never_leaks_cc_content(case_id: str, turns: int) -> None:
    avatar = StubAvatar(MagicMock())
    msg = await avatar.next_message(
        FSMState.TRAINING,
        SessionContext(product_id=case_id, dialog_history=_history(turns)),
    )
    for marker in _CC_MARKERS:
        assert marker not in msg, f"{case_id}/{turns}: утечка cc_novichok — {msg[:120]!r}"


@pytest.mark.asyncio
async def test_training_stub_uses_own_case_theory() -> None:
    avatar = StubAvatar(MagicMock())
    msg = await avatar.next_message(
        FSMState.TRAINING, SessionContext(product_id="xpv", dialog_history=_history(0))
    )
    assert "ХПВ" in msg


@pytest.mark.asyncio
async def test_training_stub_output_is_clean() -> None:
    # Текст стаба идёт в чат напрямую: без markdown и без номеров пунктов.
    avatar = StubAvatar(MagicMock())
    for turns in range(4):
        msg = await avatar.next_message(
            FSMState.TRAINING,
            SessionContext(product_id="xpv", dialog_history=_history(turns)),
        )
        assert "**" not in msg
        assert not msg[0].isdigit()


@pytest.mark.asyncio
@pytest.mark.parametrize("case_id", _TECHNIQUES)
async def test_roleplay_states_never_leak_cc_content(case_id: str) -> None:
    avatar = StubAvatar(MagicMock())
    for state in (FSMState.EXAMPLE, FSMState.PRACTICE, FSMState.TRAINING_QUIZ):
        msg = await avatar.next_message(
            state, SessionContext(product_id=case_id, dialog_history=_history(1))
        )
        for marker in _CC_MARKERS:
            assert marker not in msg, f"{case_id}/{state}: утечка — {msg[:120]!r}"


@pytest.mark.asyncio
async def test_cc_novichok_still_uses_curated_blocks() -> None:
    avatar = StubAvatar(MagicMock())
    msg = await avatar.next_message(
        FSMState.TRAINING, SessionContext(product_id="cc_novichok", dialog_history=_history(0))
    )
    assert "запасной кошелёк" in msg
