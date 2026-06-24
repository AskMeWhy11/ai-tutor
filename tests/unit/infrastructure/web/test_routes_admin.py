"""Доступ к админке: 401 без креды, 200 с верными, 503 при пустом пароле.

Плюс download/upload файлов кейса cc_novichok.
"""

from __future__ import annotations

from base64 import b64encode
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from composition.app import create_app
from infrastructure.config import Settings
from infrastructure.content import case_loader


def _basic(user: str, password: str) -> dict[str, str]:
    token = b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _make_settings(tmp_path: Path, *, password: str = "s3cret") -> Settings:
    return Settings.model_validate(
        {
            "prompts_path": str(tmp_path / "prompts.json"),
            "tts_cache_dir": str(tmp_path / "tts-cache"),
            "salutespeech_enabled": False,
            "admin_username": "root",
            "admin_password": password,
        }
    )


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return _make_settings(tmp_path)


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings=settings))


@pytest.fixture
def auth() -> dict[str, str]:
    return _basic("root", "s3cret")


def test_admin_get_requires_auth(client: TestClient) -> None:
    res = client.get("/admin/prompts")
    assert res.status_code == 401
    assert "WWW-Authenticate" in res.headers


def test_admin_get_rejects_wrong_password(client: TestClient) -> None:
    res = client.get("/admin/prompts", headers=_basic("root", "wrong"))
    assert res.status_code == 401


def test_admin_get_accepts_valid_credentials(client: TestClient, auth: dict[str, str]) -> None:
    res = client.get("/admin/prompts", headers=auth)
    assert res.status_code == 200
    assert "Админка" in res.text


def test_admin_post_requires_auth(client: TestClient) -> None:
    res = client.post("/admin/prompts", data={"system_prompt": "x"})
    assert res.status_code == 401


def test_admin_disabled_when_password_empty(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path, password="")
    client = TestClient(create_app(settings=settings))
    res = client.get("/admin/prompts", headers=_basic("admin", "anything"))
    assert res.status_code == 503


# ---------- case files: download / upload ----------


def test_case_download_requires_auth(client: TestClient) -> None:
    res = client.get("/admin/case/cc_novichok/facts")
    assert res.status_code == 401


def test_case_download_facts(client: TestClient, auth: dict[str, str]) -> None:
    res = client.get("/admin/case/cc_novichok/facts", headers=auth)
    assert res.status_code == 200
    assert "markdown" in res.headers["content-type"]
    assert "facts.md" in res.headers.get("content-disposition", "")


def test_case_download_dialogues(client: TestClient, auth: dict[str, str]) -> None:
    res = client.get("/admin/case/cc_novichok/dialogues", headers=auth)
    assert res.status_code == 200
    assert "dialogues.md" in res.headers.get("content-disposition", "")


def test_case_download_unknown_case(client: TestClient, auth: dict[str, str]) -> None:
    res = client.get("/admin/case/unknown/facts", headers=auth)
    assert res.status_code == 404


def test_case_download_unknown_file(client: TestClient, auth: dict[str, str]) -> None:
    res = client.get("/admin/case/cc_novichok/readme", headers=auth)
    assert res.status_code == 404


def test_case_upload_requires_auth(client: TestClient) -> None:
    res = client.post(
        "/admin/case/cc_novichok/facts",
        files={"file": ("facts.md", b"# new", "text/markdown")},
    )
    assert res.status_code == 401


def test_case_upload_writes_file_and_invalidates_cache(
    client: TestClient,
    auth: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Перенаправляем _CASES_DIR во временную папку, чтобы не трогать боевой контент.
    fake_cases = tmp_path / "cases"
    (fake_cases / "cc_novichok").mkdir(parents=True)
    (fake_cases / "cc_novichok" / "facts.md").write_text("old", encoding="utf-8")
    monkeypatch.setattr(case_loader, "_CASES_DIR", fake_cases)
    case_loader.invalidate_case_cache()
    assert case_loader.load_case("cc_novichok").facts == "old"

    new_text = "## Welcome\nПривет, новый кейс!\n\n## Other\nfoo"
    res = client.post(
        "/admin/case/cc_novichok/facts",
        headers=auth,
        files={"file": ("facts.md", new_text.encode("utf-8"), "text/markdown")},
    )
    assert res.status_code == 200  # после редиректа TestClient следует за 303 → GET 200

    # Файл записан, кэш сброшен.
    assert (fake_cases / "cc_novichok" / "facts.md").read_text(encoding="utf-8") == new_text
    assert "новый кейс" in case_loader.load_case("cc_novichok").facts


def test_case_upload_rejects_non_utf8(
    client: TestClient,
    auth: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_cases = tmp_path / "cases"
    (fake_cases / "cc_novichok").mkdir(parents=True)
    monkeypatch.setattr(case_loader, "_CASES_DIR", fake_cases)

    res = client.post(
        "/admin/case/cc_novichok/facts",
        headers=auth,
        files={"file": ("facts.md", b"\xff\xfe\xfa", "text/markdown")},
    )
    assert res.status_code == 400


def test_case_upload_rejects_too_large(
    client: TestClient,
    auth: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_cases = tmp_path / "cases"
    (fake_cases / "cc_novichok").mkdir(parents=True)
    monkeypatch.setattr(case_loader, "_CASES_DIR", fake_cases)

    big = ("a" * (1024 * 1024 + 1)).encode("utf-8")
    res = client.post(
        "/admin/case/cc_novichok/facts",
        headers=auth,
        files={"file": ("facts.md", big, "text/markdown")},
    )
    assert res.status_code == 413


# ---------- restore из default/ ----------


def _setup_fake_cases(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    fake_cases = tmp_path / "cases"
    case = fake_cases / "cc_novichok"
    default = case / "default"
    default.mkdir(parents=True)
    (case / "facts.md").write_text("CURRENT facts", encoding="utf-8")
    (default / "facts.md").write_text("DEFAULT facts", encoding="utf-8")
    (case / "dialogues.md").write_text("CURRENT dialogues", encoding="utf-8")
    (default / "dialogues.md").write_text("DEFAULT dialogues", encoding="utf-8")
    (case / "checklist.json").write_text('{"needs": []}', encoding="utf-8")
    (default / "checklist.json").write_text(
        '{"needs": [{"id": "N1", "name": "x", "criteria": "y",'
        ' "example_phrases": ["a"], "keywords": ["k"]}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(case_loader, "_CASES_DIR", fake_cases)
    case_loader.invalidate_case_cache()
    return fake_cases


def test_restore_requires_auth(client: TestClient) -> None:
    res = client.post(
        "/admin/case/cc_novichok/facts/restore",
        follow_redirects=False,
    )
    assert res.status_code == 401


def test_restore_facts_from_default(
    client: TestClient,
    auth: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = _setup_fake_cases(monkeypatch, tmp_path)
    res = client.post(
        "/admin/case/cc_novichok/facts/restore",
        headers=auth,
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert (fake / "cc_novichok" / "facts.md").read_text(encoding="utf-8") == "DEFAULT facts"
    assert case_loader.load_case("cc_novichok").facts == "DEFAULT facts"


def test_restore_checklist_from_default(
    client: TestClient,
    auth: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _setup_fake_cases(monkeypatch, tmp_path)
    res = client.post(
        "/admin/case/cc_novichok/checklist/restore",
        headers=auth,
        follow_redirects=False,
    )
    assert res.status_code == 303
    cl = case_loader.load_case("cc_novichok").checklist
    assert cl.get("needs") and cl["needs"][0].id == "N1"


def test_restore_missing_default_returns_404(
    client: TestClient,
    auth: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_cases = tmp_path / "cases"
    (fake_cases / "cc_novichok").mkdir(parents=True)
    (fake_cases / "cc_novichok" / "facts.md").write_text("x", encoding="utf-8")
    monkeypatch.setattr(case_loader, "_CASES_DIR", fake_cases)
    res = client.post(
        "/admin/case/cc_novichok/facts/restore",
        headers=auth,
        follow_redirects=False,
    )
    assert res.status_code == 404


def test_restore_unknown_file_key_404(
    client: TestClient,
    auth: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _setup_fake_cases(monkeypatch, tmp_path)
    res = client.post(
        "/admin/case/cc_novichok/readme/restore",
        headers=auth,
        follow_redirects=False,
    )
    assert res.status_code == 404


# ---------- checklist editor ----------


def test_checklist_save_updates_file_and_cache(
    client: TestClient,
    auth: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = _setup_fake_cases(monkeypatch, tmp_path)

    form = {
        "cl__needs__0__id": "N1",
        "cl__needs__0__name": "Уточнил формат",
        "cl__needs__0__criteria": "Спросил про наличные/безнал",
        "cl__needs__0__example_phrases": "Наличные или картой?\nКуда тратить?",
        "cl__needs__0__keywords": "налич\nкарт",
        "cl__pitch__0__id": "P1",
        "cl__pitch__0__name": "Выбрал карту",
        "cl__pitch__0__criteria": "Подобрал под потребность",
        "cl__pitch__0__example_phrases": "",
        "cl__pitch__0__keywords": "",
    }
    res = client.post(
        "/admin/case/cc_novichok/checklist/edit",
        headers=auth,
        data=form,
        follow_redirects=False,
    )
    assert res.status_code == 303

    import json as _json

    saved = _json.loads((fake / "cc_novichok" / "checklist.json").read_text(encoding="utf-8"))
    assert saved["needs"][0]["id"] == "N1"
    assert saved["needs"][0]["example_phrases"] == ["Наличные или картой?", "Куда тратить?"]
    assert saved["needs"][0]["keywords"] == ["налич", "карт"]
    assert saved["pitch"][0]["id"] == "P1"
    assert saved["conditions"] == []

    # Кэш сброшен — load_case видит новые данные.
    cl = case_loader.load_case("cc_novichok").checklist
    assert cl["needs"][0].keywords == ("налич", "карт")


def test_checklist_delete_item(
    client: TestClient,
    auth: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = _setup_fake_cases(monkeypatch, tmp_path)

    form = {
        "cl__needs__0__id": "N1",
        "cl__needs__0__name": "first",
        "cl__needs__0__criteria": "c1",
        "cl__needs__0__example_phrases": "",
        "cl__needs__0__keywords": "",
        "cl__needs__1__id": "N2",
        "cl__needs__1__name": "second",
        "cl__needs__1__criteria": "c2",
        "cl__needs__1__example_phrases": "",
        "cl__needs__1__keywords": "",
        "delete__needs__0": "on",
    }
    res = client.post(
        "/admin/case/cc_novichok/checklist/edit",
        headers=auth,
        data=form,
        follow_redirects=False,
    )
    assert res.status_code == 303
    import json as _json

    saved = _json.loads((fake / "cc_novichok" / "checklist.json").read_text(encoding="utf-8"))
    ids = [it["id"] for it in saved["needs"]]
    assert ids == ["N2"]


def test_checklist_add_appends_empty_item(
    client: TestClient,
    auth: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = _setup_fake_cases(monkeypatch, tmp_path)

    form = {
        "cl__pitch__0__id": "P1",
        "cl__pitch__0__name": "first",
        "cl__pitch__0__criteria": "c",
        "cl__pitch__0__example_phrases": "",
        "cl__pitch__0__keywords": "",
        "action": "add_pitch",
    }
    res = client.post(
        "/admin/case/cc_novichok/checklist/edit",
        headers=auth,
        data=form,
        follow_redirects=False,
    )
    assert res.status_code == 303

    import json as _json

    saved = _json.loads((fake / "cc_novichok" / "checklist.json").read_text(encoding="utf-8"))
    assert len(saved["pitch"]) == 2
    assert saved["pitch"][0]["id"] == "P1"
    assert saved["pitch"][1] == {
        "id": "",
        "name": "",
        "criteria": "",
        "example_phrases": [],
        "keywords": [],
    }


def test_checklist_save_requires_auth(client: TestClient) -> None:
    res = client.post(
        "/admin/case/cc_novichok/checklist/edit",
        data={"cl__needs__0__id": "x"},
        follow_redirects=False,
    )
    assert res.status_code == 401


def test_checklist_save_unknown_case_404(
    client: TestClient,
    auth: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _setup_fake_cases(monkeypatch, tmp_path)
    res = client.post(
        "/admin/case/unknown/checklist/edit",
        headers=auth,
        data={"cl__needs__0__id": "x"},
        follow_redirects=False,
    )
    assert res.status_code == 404


# ---------- мультикейс: селектор и изоляция промптов ----------


def test_prompts_page_has_case_selector(client: TestClient, auth: dict[str, str]) -> None:
    res = client.get("/admin/prompts", headers=auth)
    assert res.status_code == 200
    assert 'name="case_id"' in res.text
    assert 'value="xpv"' in res.text


def test_prompts_page_unknown_case_falls_back(client: TestClient, auth: dict[str, str]) -> None:
    res = client.get("/admin/prompts?case_id=nope", headers=auth)
    assert res.status_code == 200  # _resolve_case_id → DEFAULT


def test_prompts_post_isolated_per_case(
    client: TestClient,
    auth: dict[str, str],
    settings: Settings,
) -> None:
    from infrastructure.llm.prompt_store import PromptStore

    store = PromptStore(settings.prompts_file)
    base = store.snapshot("xpv")
    form: dict[str, str] = {
        "case_id": "xpv",
        "system_prompt": base.system_prompt,
        "stage_director_prompt": base.stage_director_prompt,
        "quiz_prompt": "XPV-QUIZ",
        "mode__training": "XPV-TRAINING-PROMPT",
    }
    res = client.post("/admin/prompts", headers=auth, data=form, follow_redirects=False)
    assert res.status_code == 303
    assert "case_id=xpv" in res.headers["location"]

    reloaded = PromptStore(settings.prompts_file)
    from domain.states import Mode

    assert reloaded.get_quiz_prompt("xpv") == "XPV-QUIZ"
    assert reloaded.get_mode_prompt(Mode.TRAINING, "xpv") == "XPV-TRAINING-PROMPT"
    # cc_novichok не затронут.
    assert reloaded.get_quiz_prompt("cc_novichok") != "XPV-QUIZ"


def test_case_files_routes_work_for_new_case(
    client: TestClient,
    auth: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_cases = tmp_path / "cases"
    (fake_cases / "xpv").mkdir(parents=True)
    (fake_cases / "xpv" / "facts.md").write_text("XPV facts", encoding="utf-8")
    monkeypatch.setattr(case_loader, "_CASES_DIR", fake_cases)
    res = client.get("/admin/case/xpv/facts", headers=auth)
    assert res.status_code == 200
    assert "facts.md" in res.headers.get("content-disposition", "")
