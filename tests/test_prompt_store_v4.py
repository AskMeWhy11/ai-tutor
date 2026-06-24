from __future__ import annotations

import json
from pathlib import Path

from infrastructure.llm.prompt_store import PromptStore

_SCHEMA_VERSION = 5


def test_default_includes_stage_director(tmp_path: Path):
    p = tmp_path / "prompts.json"
    store = PromptStore(p)
    snap = store.snapshot()
    assert snap.stage_director_prompt.strip() != ""
    assert (
        "судья" in snap.stage_director_prompt.lower()
        or "stage" in snap.stage_director_prompt.lower()
    )


def test_replace_all_persists_stage_director(tmp_path: Path):
    p = tmp_path / "prompts.json"
    store = PromptStore(p)
    snap = store.snapshot()
    store.replace_all(
        system_prompt=snap.system_prompt,
        templates=snap.templates,
        mode_prompts=snap.mode_prompts,
        quiz_prompt=snap.quiz_prompt,
        stage_director_prompt="custom sd prompt",
    )

    raw = json.loads(p.read_text(encoding="utf-8"))
    assert raw["stage_director_prompt"] == "custom sd prompt"
    assert raw["version"] == _SCHEMA_VERSION

    # Перечитали — значение сохранилось.
    store2 = PromptStore(p)
    assert store2.get_stage_director_prompt() == "custom sd prompt"


def test_legacy_file_without_stage_director_is_upgraded(tmp_path: Path):
    p = tmp_path / "prompts.json"
    p.write_text(
        json.dumps(
            {
                "version": 3,
                "system_prompt": "",
                "templates": {},
                "mode_prompts": {},
                "quiz_prompt": "old quiz",
            }
        ),
        encoding="utf-8",
    )
    store = PromptStore(p)
    sd = store.get_stage_director_prompt()
    assert sd.strip() != ""  # подтянулся дефолт
    assert store.get_quiz_prompt() == "old quiz"


def test_legacy_mode_quiz_migrated_to_default_case(tmp_path: Path):
    """v4 без cases: legacy mode_prompts/quiz_prompt уезжают в DEFAULT_CASE_ID."""
    from domain.states import Mode
    from infrastructure.content.registry import DEFAULT_CASE_ID

    p = tmp_path / "prompts.json"
    p.write_text(
        json.dumps(
            {
                "version": 4,
                "system_prompt": "SP",
                "templates": {},
                "stage_director_prompt": "sd",
                "mode_prompts": {Mode.TRAINING.value: "LEGACY TRAINING"},
                "quiz_prompt": "legacy quiz",
            }
        ),
        encoding="utf-8",
    )
    store = PromptStore(p)
    # В дефолтном кейсе — мигрированные значения.
    assert store.get_mode_prompt(Mode.TRAINING, DEFAULT_CASE_ID) == "LEGACY TRAINING"
    assert store.get_quiz_prompt(DEFAULT_CASE_ID) == "legacy quiz"
    # В другом кейсе — дефолты (не legacy).
    assert store.get_mode_prompt(Mode.TRAINING, "xpv") != "LEGACY TRAINING"


def test_v5_cases_roundtrip(tmp_path: Path):
    from domain.states import Mode

    p = tmp_path / "prompts.json"
    store = PromptStore(p)
    snap = store.snapshot("xpv")
    store.replace_all(
        system_prompt=snap.system_prompt,
        templates=snap.templates,
        mode_prompts={**snap.mode_prompts, Mode.PRACTICE: "XPV PRACTICE"},
        quiz_prompt="xpv quiz",
        stage_director_prompt=snap.stage_director_prompt,
        case_id="xpv",
    )
    raw = json.loads(p.read_text(encoding="utf-8"))
    assert raw["version"] == _SCHEMA_VERSION
    assert raw["cases"]["xpv"]["quiz_prompt"] == "xpv quiz"

    store2 = PromptStore(p)
    assert store2.get_mode_prompt(Mode.PRACTICE, "xpv") == "XPV PRACTICE"
    # cc_novichok не затронут.
    assert store2.get_quiz_prompt("cc_novichok") != "xpv quiz"
