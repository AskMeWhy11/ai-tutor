"""Миграции PromptStore со старых схем (v3/v4/v5) на актуальную v8.

Исторические ожидания:
* v<6 — mode/quiz хранили отрендеренный контент → при миграции сбрасываются
  к дефолтным шаблонам с плейсхолдерами (кастомные тексты теряются осознанно);
* v<7 — глобальный stage_director_prompt переезжает в bundle DEFAULT_CASE_ID;
* v8 — эталонный нейминг плейсхолдеров, per-case структура;
* v9 — stage_director разделён по режимам (общий текст копируется в 4 поля).
"""

from __future__ import annotations

import json
from pathlib import Path

from domain.states import Mode
from infrastructure.content.registry import DEFAULT_CASE_ID
from infrastructure.llm.prompt_store import PromptStore

_SCHEMA_VERSION = 9


def test_default_includes_stage_director(tmp_path: Path):
    p = tmp_path / "prompts.json"
    store = PromptStore(p)
    snap = store.snapshot()
    assert set(snap.stage_director_prompts) == set(Mode)
    for text in snap.stage_director_prompts.values():
        assert text.strip() != ""
        assert "судья" in text.lower() or "stage" in text.lower()


def test_replace_all_persists_stage_director(tmp_path: Path):
    p = tmp_path / "prompts.json"
    store = PromptStore(p)
    snap = store.snapshot()
    store.replace_all(
        system_prompt=snap.system_prompt,
        templates=snap.templates,
        mode_prompts=snap.mode_prompts,
        quiz_prompt=snap.quiz_prompt,
        stage_director_prompts={Mode.EXAMPLE: "custom sd prompt"},
    )

    raw = json.loads(p.read_text(encoding="utf-8"))
    # v9: stage_director_prompts — per-mode dict внутри cases.
    sd_raw = raw["cases"][DEFAULT_CASE_ID]["stage_director_prompts"]
    assert sd_raw[Mode.EXAMPLE.value] == "custom sd prompt"
    assert raw["version"] == _SCHEMA_VERSION

    # Перечитали — значение сохранилось; другие режимы не задеты.
    store2 = PromptStore(p)
    assert store2.get_stage_director_prompt(Mode.EXAMPLE) == "custom sd prompt"
    assert store2.get_stage_director_prompt(Mode.TRAINING) != "custom sd prompt"


def test_legacy_v3_upgraded_with_defaults(tmp_path: Path):
    """v3: кастомные mode/quiz содержали отрендеренный контент → сбрасываются."""
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
    sd = store.get_stage_director_prompt(Mode.TRAINING)
    assert sd.strip() != ""  # подтянулся дефолт
    # v<6 → legacy quiz осознанно затирается свежим дефолтом с плейсхолдерами.
    assert store.get_quiz_prompt() != "old quiz"
    assert store.get_quiz_prompt().strip() != ""
    # Файл переписан в актуальную схему.
    assert json.loads(p.read_text(encoding="utf-8"))["version"] == _SCHEMA_VERSION


def test_legacy_v4_mode_quiz_reset_to_defaults(tmp_path: Path):
    """v4 без cases: legacy mode/quiz (отрендеренные) сбрасываются к дефолтам."""
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
    # Кастомный (вшитый) текст затёрт, дефолт содержит эталонный плейсхолдер.
    training = store.snapshot(DEFAULT_CASE_ID).mode_prompts[Mode.TRAINING]
    assert training != "LEGACY TRAINING"
    assert "{PRODUCT_DETAILS}" in training
    # Изменённый админом stage_director раскладывается во все 4 режимных поля
    # DEFAULT_CASE_ID (миграция без потери контента).
    assert all(v == "sd" for v in store.snapshot(DEFAULT_CASE_ID).stage_director_prompts.values())
    assert store.snapshot("xpv").stage_director_prompts[Mode.TRAINING] != "sd"


def test_v9_cases_roundtrip(tmp_path: Path):
    p = tmp_path / "prompts.json"
    store = PromptStore(p)
    snap = store.snapshot("xpv")
    store.replace_all(
        system_prompt=snap.system_prompt,
        templates=snap.templates,
        mode_prompts={**snap.mode_prompts, Mode.PRACTICE: "XPV PRACTICE"},
        quiz_prompt="xpv quiz",
        stage_director_prompts=snap.stage_director_prompts,
        case_id="xpv",
    )
    raw = json.loads(p.read_text(encoding="utf-8"))
    assert raw["version"] == _SCHEMA_VERSION
    assert raw["cases"]["xpv"]["quiz_prompt"] == "xpv quiz"

    store2 = PromptStore(p)
    assert store2.get_mode_prompt(Mode.PRACTICE, "xpv") == "XPV PRACTICE"
    # cc_novichok не затронут.
    assert store2.get_quiz_prompt("cc_novichok") != "xpv quiz"
