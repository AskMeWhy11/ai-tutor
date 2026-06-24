from __future__ import annotations

import pytest

from infrastructure.content import case_loader


@pytest.fixture(autouse=True)
def _clear_cache():
    case_loader.load_case.cache_clear()
    yield
    case_loader.load_case.cache_clear()


def test_load_case_reads_files(tmp_path, monkeypatch):
    root = tmp_path / "cases"
    case_dir = root / "demo"
    case_dir.mkdir(parents=True)
    (case_dir / "facts.md").write_text("# Facts\n\n## Welcome\nПривет!\n", encoding="utf-8")
    (case_dir / "dialogues.md").write_text("# D\n\n- реплика", encoding="utf-8")

    monkeypatch.setattr(case_loader, "_CASES_DIR", root)

    case = case_loader.load_case("demo")
    assert case.case_id == "demo"
    assert "Welcome" in case.facts
    assert "реплика" in case.dialogues


def test_load_case_missing_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(case_loader, "_CASES_DIR", tmp_path)
    case = case_loader.load_case("nope")
    assert case.facts == ""
    assert case.dialogues == ""


def test_load_case_is_cached(tmp_path, monkeypatch):
    case_dir = tmp_path / "x"
    case_dir.mkdir()
    (case_dir / "facts.md").write_text("v1", encoding="utf-8")
    (case_dir / "dialogues.md").write_text("", encoding="utf-8")
    monkeypatch.setattr(case_loader, "_CASES_DIR", tmp_path)

    a = case_loader.load_case("x")
    (case_dir / "facts.md").write_text("v2", encoding="utf-8")
    b = case_loader.load_case("x")
    assert a.facts == b.facts == "v1"  # кэш
