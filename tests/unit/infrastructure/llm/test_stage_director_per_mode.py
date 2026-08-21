"""Тесты v9: StageDirector по режимам — миграция, wiring, YAML-встраивание."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from domain.states import Mode
from infrastructure.content.registry import DEFAULT_CASE_ID
from infrastructure.llm.default_prompts import (
    default_stage_director_prompts,
    embed_stage_criteria,
)
from infrastructure.llm.prompt_store import PromptStore
from infrastructure.llm.yaml_export import export_prompts_yaml

pytestmark = pytest.mark.unit


# ---------- дефолты по режимам ----------


def test_default_sd_prompts_per_mode_scoped() -> None:
    d = default_stage_director_prompts(DEFAULT_CASE_ID)
    assert set(d) == set(Mode)
    # Общая база — в каждом режиме.
    for text in d.values():
        assert "ОБЩИЕ ПРАВИЛА" in text
        assert "ФОРМАТ ОТВЕТА" in text
    # Режимные правила — строго в своём режиме.
    assert "example_refused_3x" not in d[Mode.TRAINING]
    assert "practice_accepted" not in d[Mode.EXAMPLE]
    assert "training_understood" not in d[Mode.PRACTICE]


def test_default_sd_technique_training_has_facts_block() -> None:
    tech = default_stage_director_prompts("xpv")
    assert "{PRODUCT_DETAILS}" in tech[Mode.TRAINING]
    for mode in (Mode.EXAMPLE, Mode.PRACTICE, Mode.KNOWLEDGE):
        assert "{PRODUCT_DETAILS}" not in tech[mode]
    default = default_stage_director_prompts(DEFAULT_CASE_ID)
    assert "{PRODUCT_DETAILS}" not in default[Mode.TRAINING]


# ---------- prompt_store: миграция v8 → v9 ----------


def test_v8_single_sd_migrates_to_all_modes(tmp_path: Path) -> None:
    payload = {
        "version": 8,
        "system_prompt": "",
        "templates": {},
        "cases": {
            "xpv": {
                "mode_prompts": {},
                "quiz_prompt": "q",
                "stage_director_prompt": "CUSTOM SD TEXT",
            }
        },
    }
    path = tmp_path / "prompts.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    store = PromptStore(path)
    snap = store.snapshot("xpv")
    # Без потери контента: общий текст разложен во все 4 режимных поля.
    assert all(v == "CUSTOM SD TEXT" for v in snap.stage_director_prompts.values())
    # Другие кейсы получают режимные дефолты.
    other = store.snapshot(DEFAULT_CASE_ID)
    assert other.stage_director_prompts[Mode.TRAINING] != "CUSTOM SD TEXT"


def test_v9_sd_roundtrip_per_mode(tmp_path: Path) -> None:
    path = tmp_path / "prompts.json"
    store = PromptStore(path)
    snap = store.snapshot(DEFAULT_CASE_ID)
    store.replace_all(
        system_prompt=snap.system_prompt,
        templates=snap.templates,
        stage_director_prompts={Mode.PRACTICE: "SD-PRACTICE-EDITED"},
        case_id=DEFAULT_CASE_ID,
    )
    reloaded = PromptStore(path)
    assert reloaded.get_stage_director_prompt(Mode.PRACTICE) == "SD-PRACTICE-EDITED"
    # Остальные режимы не задеты.
    assert reloaded.get_stage_director_prompt(Mode.EXAMPLE) != "SD-PRACTICE-EDITED"


def test_restore_stage_director_prompt(tmp_path: Path) -> None:
    path = tmp_path / "prompts.json"
    store = PromptStore(path)
    store.replace_all(
        system_prompt="",
        templates={},
        stage_director_prompts={Mode.EXAMPLE: "EDITED"},
        case_id="xpv",
    )
    restored = store.restore_stage_director_prompt(Mode.EXAMPLE, "xpv")
    assert restored == default_stage_director_prompts("xpv")[Mode.EXAMPLE]
    assert store.snapshot("xpv").stage_director_prompts[Mode.EXAMPLE] == restored


# ---------- gigachat_stage_director: промпт своего режима ----------


def test_stage_director_uses_mode_prompt() -> None:
    from domain.states import FSMState
    from infrastructure.llm.gigachat_stage_director import _STATE_TO_MODE

    assert _STATE_TO_MODE[FSMState.TRAINING] is Mode.TRAINING
    assert _STATE_TO_MODE[FSMState.EXAMPLE] is Mode.EXAMPLE
    assert _STATE_TO_MODE[FSMState.PRACTICE] is Mode.PRACTICE
    assert _STATE_TO_MODE[FSMState.KNOWLEDGE] is Mode.KNOWLEDGE


# ---------- QUIZ: общий system prompt подаётся ----------


async def test_quiz_director_prepends_global_system_prompt(tmp_path: Path) -> None:
    from domain.context import SessionContext
    from infrastructure.llm.gigachat_quiz_director import GigaChatQuizDirector
    from infrastructure.llm.stub_quiz_director import StubQuizDirector

    store = PromptStore(tmp_path / "prompts.json")
    snap = store.snapshot()
    store.replace_all(system_prompt="GLOBAL-SYSTEM-RULE", templates=snap.templates)

    captured: list[list[tuple[str, str]]] = []

    class _FakeClient:
        pass

    director = GigaChatQuizDirector(
        client=_FakeClient(),  # type: ignore[arg-type]
        prompt_store=store,
        fallback=StubQuizDirector(),
    )

    async def _fake_chat(messages: list[tuple[str, str]]) -> str:
        captured.append(messages)
        return '{"verdict": "none", "explanation": "", "next_question": "q", "done": false}'

    director._chat = _fake_chat  # type: ignore[method-assign]
    await director.next_turn(SessionContext(product_id="cc_novichok"), None)

    assert captured, "LLM не вызван"
    role, system_text = captured[0][0]
    assert role == "system"
    assert system_text.startswith("GLOBAL-SYSTEM-RULE")
    # Промпт квиза тоже на месте (конкатенация, а не замена).
    assert len(system_text) > len("GLOBAL-SYSTEM-RULE") + 10


# ---------- YAML: критерии внутри блока режима ----------


def test_embed_stage_criteria_format() -> None:
    out = embed_stage_criteria("MODE PROMPT", "SD CRITERIA", "cc-novichok")
    assert out.startswith("MODE PROMPT")
    assert "КРИТЕРИИ ЗАВЕРШЕНИЯ СТАДИИ (cc-novichok-learning-check):" in out
    assert out.rstrip().endswith("SD CRITERIA")
    # Пустые критерии — блок не добавляется.
    assert embed_stage_criteria("MODE PROMPT", "  ", "x") == "MODE PROMPT"


def test_export_embeds_criteria_per_mode_no_common_section(tmp_path: Path) -> None:
    store = PromptStore(tmp_path / "prompts.json")
    store.replace_all(
        system_prompt="",
        templates={},
        stage_director_prompts={
            Mode.TRAINING: "SD-T",
            Mode.EXAMPLE: "SD-E",
            Mode.PRACTICE: "SD-P",
            Mode.KNOWLEDGE: "SD-K",
        },
        case_id=DEFAULT_CASE_ID,
    )
    out = export_prompts_yaml(store, DEFAULT_CASE_ID)
    # Отдельного общего ключа нет.
    assert "-learning-check-prompt:" not in out

    def block(key: str) -> str:
        start = out.index(f"    {key}: |")
        rest = out[start + len(key) + 7 :]
        nxt = rest.find(": |")
        return rest[: nxt if nxt != -1 else len(rest)]

    assert "SD-T" in block("cc-novichok-learning-transcription-prompt")
    assert "SD-E" in block("cc-novichok-client-transcription-prompt")
    assert "SD-P" in block("cc-novichok-employee-transcription-prompt")
    assert "SD-K" in block("cc-novichok-mentor-transcription-prompt")
    # Критерии не перепутаны между режимами.
    assert "SD-P" not in block("cc-novichok-learning-transcription-prompt")
