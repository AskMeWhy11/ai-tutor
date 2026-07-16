import json
from pathlib import Path

import pytest

from domain.states import Mode
from infrastructure.llm.prompt_store import PromptStore


def _patch_content(monkeypatch: pytest.MonkeyPatch) -> None:
    import infrastructure.llm.content_render as mod

    class _Case:
        facts = "ДИНАМИЧЕСКИЕ_ФАКТЫ"
        dialogues = "ДИНАМИЧЕСКИЕ_ДИАЛОГИ"

    monkeypatch.setattr(mod, "load_case", lambda cid: _Case())
    monkeypatch.setattr(mod, "resolve_case_id", lambda cid: cid or "cc_novichok")


def test_get_mode_prompt_renders_content(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_content(monkeypatch)
    store = PromptStore(tmp_path / "prompts.json")

    text = store.get_mode_prompt(Mode.TRAINING)
    assert "ДИНАМИЧЕСКИЕ_ФАКТЫ" in text
    assert "{FACTS}" not in text


def test_snapshot_keeps_template(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_content(monkeypatch)
    store = PromptStore(tmp_path / "prompts.json")

    snap = store.snapshot()
    # В админку отдаётся ШАБЛОН с плейсхолдерами, не отрендеренный текст.
    assert "{FACTS}" in snap.mode_prompts[Mode.TRAINING]


def test_stored_file_has_no_rendered_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_content(monkeypatch)
    store = PromptStore(tmp_path / "prompts.json")
    store.get_mode_prompt(Mode.TRAINING)  # триггерим flush

    raw = json.loads((tmp_path / "prompts.json").read_text(encoding="utf-8"))
    assert raw["version"] == 7
    dumped = json.dumps(raw, ensure_ascii=False)
    assert "ДИНАМИЧЕСКИЕ_ФАКТЫ" not in dumped  # контент НЕ вшит в файл
    assert "{FACTS}" in dumped


def test_v5_migration_resets_case_prompts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_content(monkeypatch)
    path = tmp_path / "prompts.json"
    # Старый v5 с отрендеренным (устаревшим) контентом в mode_prompts.
    path.write_text(
        json.dumps(
            {
                "version": 5,
                "system_prompt": "sys",
                "templates": {},
                "stage_director_prompt": "sd",
                "cases": {
                    "cc_novichok": {
                        "mode_prompts": {"training": "СТАРЫЙ ВШИТЫЙ ТЕКСТ"},
                        "quiz_prompt": "СТАРЫЙ КВИЗ",
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    store = PromptStore(path)
    snap = store.snapshot("cc_novichok")
    # После миграции — дефолтный шаблон с плейсхолдером, старьё затёрто.
    assert "{FACTS}" in snap.mode_prompts[Mode.TRAINING]
    assert "СТАРЫЙ ВШИТЫЙ ТЕКСТ" not in snap.mode_prompts[Mode.TRAINING]
