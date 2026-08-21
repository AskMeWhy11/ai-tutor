"""Тесты файлового PromptStore."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from domain.states import FSMState
from infrastructure.llm.prompt_store import (
    DYNAMIC_STATES,
    EDITABLE_STATES,
    PromptStore,
    default_templates,
)


@pytest.fixture
def store_path(tmp_path: Path) -> Path:
    return tmp_path / "prompts" / "templates.json"


def test_first_access_creates_file_with_defaults(store_path: Path) -> None:
    store = PromptStore(path=store_path)

    snap = store.snapshot()

    assert store_path.exists()
    defaults = default_templates()
    for state in EDITABLE_STATES:
        assert snap.templates[state] == defaults[state]


def test_snapshot_contains_only_editable_states(store_path: Path) -> None:
    store = PromptStore(path=store_path)

    snap = store.snapshot()

    for state in DYNAMIC_STATES:
        assert state not in snap.templates
    for state in EDITABLE_STATES:
        assert state in snap.templates


def test_set_template_persists_to_disk(store_path: Path) -> None:
    store = PromptStore(path=store_path)
    store.set_template(FSMState.MENU, "Новое меню")

    raw = json.loads(store_path.read_text(encoding="utf-8"))
    assert raw["templates"][FSMState.MENU.value] == "Новое меню"

    # Новый экземпляр читает изменения.
    reloaded = PromptStore(path=store_path)
    assert reloaded.get_template(FSMState.MENU) == "Новое меню"


def test_set_template_rejects_dynamic_state(store_path: Path) -> None:
    store = PromptStore(path=store_path)
    dyn = next(iter(DYNAMIC_STATES))

    with pytest.raises(ValueError):
        store.set_template(dyn, "nope")


def test_replace_all_overwrites_and_ignores_dynamic(store_path: Path) -> None:
    store = PromptStore(path=store_path)
    dyn = next(iter(DYNAMIC_STATES))

    store.replace_all(
        system_prompt="SP",
        templates={FSMState.MENU: "m", dyn: "ignored"},
    )

    snap = store.snapshot()
    assert snap.system_prompt == "SP"
    assert snap.templates[FSMState.MENU] == "m"
    assert dyn not in snap.templates

    raw = json.loads(store_path.read_text(encoding="utf-8"))
    assert dyn.value not in raw["templates"]


def test_unknown_state_in_file_is_ignored(store_path: Path) -> None:
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text(
        json.dumps(
            {
                "version": 1,
                "system_prompt": "",
                "templates": {"NOT_A_STATE": "x", FSMState.MENU.value: "ok"},
            }
        ),
        encoding="utf-8",
    )

    store = PromptStore(path=store_path)
    assert store.get_template(FSMState.MENU) == "ok"


def test_corrupted_file_falls_back_to_defaults(store_path: Path) -> None:
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text("{not json", encoding="utf-8")

    store = PromptStore(path=store_path)
    snap = store.snapshot()

    defaults = default_templates()
    assert snap.templates[FSMState.MENU] == defaults[FSMState.MENU]


def test_per_case_isolation(store_path: Path) -> None:
    from domain.states import Mode
    from infrastructure.content.registry import DEFAULT_CASE_ID

    store = PromptStore(path=store_path)
    base = store.snapshot()

    store.replace_all(
        system_prompt=base.system_prompt,
        templates=base.templates,
        mode_prompts={**base.mode_prompts, Mode.TRAINING: "XPV-T"},
        stage_director_prompts=base.stage_director_prompts,
        case_id="xpv",
    )

    assert store.get_mode_prompt(Mode.TRAINING, "xpv") == "XPV-T"
    assert store.get_mode_prompt(Mode.TRAINING, DEFAULT_CASE_ID) != "XPV-T"
    assert store.snapshot("xpv").case_id == "xpv"


def test_snapshot_default_case_when_none(store_path: Path) -> None:
    from infrastructure.content.registry import DEFAULT_CASE_ID

    store = PromptStore(path=store_path)
    assert store.snapshot().case_id == DEFAULT_CASE_ID


def test_system_prompt_global_across_cases(store_path: Path) -> None:
    store = PromptStore(path=store_path)
    base = store.snapshot()
    store.replace_all(
        system_prompt="GLOBAL-SP",
        templates=base.templates,
        case_id="xpv",
    )
    # system_prompt глобальный — виден из любого кейса.
    assert store.snapshot("cc_novichok").system_prompt == "GLOBAL-SP"
    assert store.snapshot("xpv").system_prompt == "GLOBAL-SP"
