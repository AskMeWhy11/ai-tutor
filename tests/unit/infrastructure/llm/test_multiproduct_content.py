"""Мультипродуктовость: контент LLM-промптов зависит от case_id/product_id."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, cast

import pytest

from domain.context import SessionContext
from domain.types import ChatMessage, Zone
from infrastructure.content.case_loader import resolve_case_id
from infrastructure.content.registry import DEFAULT_CASE_ID
from infrastructure.llm.gigachat_quiz_director import _build_factology

if TYPE_CHECKING:
    from gigachat import GigaChat


def test_resolve_case_id_empty_falls_back_to_default() -> None:
    assert resolve_case_id("") == DEFAULT_CASE_ID
    assert resolve_case_id(None) == DEFAULT_CASE_ID


def test_resolve_case_id_unknown_falls_back_to_default() -> None:
    assert resolve_case_id("does-not-exist") == DEFAULT_CASE_ID


def test_resolve_case_id_known_kept() -> None:
    # xpv есть в реестре (available=False, но is_known_case=True)
    assert resolve_case_id("xpv") == "xpv"


def test_build_factology_returns_nonempty_for_default() -> None:
    assert _build_factology(None).strip()


def test_build_factology_unknown_case_falls_back_to_default() -> None:
    assert _build_factology("does-not-exist") == _build_factology(None)


class _SpyEvaluator:
    def __init__(self) -> None:
        self.case_ids: list[str | None] = []

    async def evaluate(
        self,
        history: tuple[ChatMessage, ...],
        *,
        case_id: str | None = None,
    ) -> tuple[Zone, ...]:
        self.case_ids.append(case_id)
        return ()


@pytest.mark.asyncio
async def test_gigachat_avatar_system_prompt_includes_case_facts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: object,
) -> None:
    from pathlib import Path

    from infrastructure.llm import gigachat_avatar as mod
    from infrastructure.llm.prompt_store import PromptStore
    from infrastructure.llm.stub_avatar import StubAvatar

    class _FakeCase:
        case_id = DEFAULT_CASE_ID
        facts = "ТЕСТ-ФАКТ-XYZ"
        dialogues = "ТЕСТ-ДИАЛОГ-ABC"
        checklist: ClassVar[dict[Zone, tuple[object, ...]]] = {}

    monkeypatch.setattr(mod, "load_case", lambda cid: _FakeCase())

    store = PromptStore(Path(cast("Path", tmp_path)) / "prompts.json")
    monkeypatch.setattr(
        store,
        "snapshot",
        lambda: type("S", (), {"system_prompt": "GLOBAL"})(),
    )

    avatar = mod.GigaChatAvatar(
        client=cast("GigaChat", object()),
        prompt_store=store,
        fallback=StubAvatar(store),
    )
    ctx = SessionContext(product_id="cc_novichok")
    prompt = avatar._compose_system_prompt("MODE-PROMPT", ctx)

    assert "ТЕСТ-ФАКТ-XYZ" in prompt
    assert "ТЕСТ-ДИАЛОГ-ABC" in prompt
    assert "MODE-PROMPT" in prompt
    assert prompt.startswith("GLOBAL")
