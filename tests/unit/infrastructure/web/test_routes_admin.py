"""Доступ к админке: cookie-логин, 303 без сессии для GET, 401 для POST,
503 при пустом пароле. Плюс download/upload файлов кейса cc_novichok.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from composition.app import create_app
from domain.states import Mode
from infrastructure.config import Settings
from infrastructure.content import case_loader
from infrastructure.web.security import ADMIN_COOKIE_NAME


def _make_settings(tmp_path: Path, *, password: str = "s3cret") -> Settings:
    return Settings.model_validate(
        {
            "prompts_path": str(tmp_path / "prompts.json"),
            "tts_cache_dir": str(tmp_path / "tts-cache"),
            "salutespeech_enabled": False,
            "admin_username": "root",
            "admin_password": password,
            # Тесты ходят по http://, secure-cookie иначе не отправится клиентом.
            "admin_cookie_secure": False,
        }
    )


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return _make_settings(tmp_path)


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings=settings))


@pytest.fixture
def auth_client(client: TestClient) -> TestClient:
    """Тот же клиент, но с валидной cookie-сессией админа."""
    res = client.post(
        "/admin/login",
        data={"username": "root", "password": "s3cret"},
        follow_redirects=False,
    )
    assert res.status_code == 303, "логин в фикстуре не прошёл"
    assert ADMIN_COOKIE_NAME in client.cookies
    return client


def test_admin_get_requires_auth(client: TestClient) -> None:
    res = client.get("/admin/prompts", follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"].startswith("/admin/login")


def test_admin_get_rejects_invalid_cookie(client: TestClient) -> None:
    client.cookies.set(ADMIN_COOKIE_NAME, "garbage")
    res = client.get("/admin/prompts", follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"].startswith("/admin/login")


def test_admin_get_accepts_valid_session(auth_client: TestClient) -> None:
    res = auth_client.get("/admin/prompts")
    assert res.status_code == 200
    assert "Админка" in res.text


def test_admin_post_requires_auth(client: TestClient) -> None:
    res = client.post("/admin/prompts", data={"system_prompt": "x"})
    assert res.status_code == 401


def test_admin_disabled_when_password_empty(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path, password="")
    client = TestClient(create_app(settings=settings))
    res = client.get("/admin/prompts", follow_redirects=False)
    assert res.status_code == 503


# ---------- case files: download / upload ----------


def test_case_download_requires_auth(client: TestClient) -> None:
    res = client.get("/admin/case/cc_novichok/facts", follow_redirects=False)
    assert res.status_code == 303


def test_case_download_facts(auth_client: TestClient) -> None:
    res = auth_client.get("/admin/case/cc_novichok/facts")
    assert res.status_code == 200
    assert "markdown" in res.headers["content-type"]
    assert "facts.md" in res.headers.get("content-disposition", "")


def test_case_download_dialogues(auth_client: TestClient) -> None:
    res = auth_client.get("/admin/case/cc_novichok/dialogues")
    assert res.status_code == 200
    assert "dialogues.md" in res.headers.get("content-disposition", "")


def test_case_download_unknown_case(auth_client: TestClient) -> None:
    res = auth_client.get("/admin/case/unknown/facts")
    assert res.status_code == 404


def test_case_download_unknown_file(auth_client: TestClient) -> None:
    res = auth_client.get("/admin/case/cc_novichok/readme")
    assert res.status_code == 404


def test_case_upload_requires_auth(client: TestClient) -> None:
    res = client.post(
        "/admin/case/cc_novichok/facts",
        files={"file": ("facts.md", b"# new", "text/markdown")},
    )
    assert res.status_code == 401


def test_case_upload_writes_file_and_invalidates_cache(
    auth_client: TestClient,
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
    res = auth_client.post(
        "/admin/case/cc_novichok/facts",
        files={"file": ("facts.md", new_text.encode("utf-8"), "text/markdown")},
    )
    assert res.status_code == 200  # после редиректа TestClient следует за 303 → GET 200

    # Файл записан, кэш сброшен.
    assert (fake_cases / "cc_novichok" / "facts.md").read_text(encoding="utf-8") == new_text
    assert "новый кейс" in case_loader.load_case("cc_novichok").facts


def test_case_upload_rejects_non_utf8(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_cases = tmp_path / "cases"
    (fake_cases / "cc_novichok").mkdir(parents=True)
    monkeypatch.setattr(case_loader, "_CASES_DIR", fake_cases)

    res = auth_client.post(
        "/admin/case/cc_novichok/facts",
        files={"file": ("facts.md", b"\xff\xfe\xfa", "text/markdown")},
    )
    assert res.status_code == 400


def test_case_upload_rejects_too_large(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_cases = tmp_path / "cases"
    (fake_cases / "cc_novichok").mkdir(parents=True)
    monkeypatch.setattr(case_loader, "_CASES_DIR", fake_cases)

    big = ("a" * (1024 * 1024 + 1)).encode("utf-8")
    res = auth_client.post(
        "/admin/case/cc_novichok/facts",
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
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = _setup_fake_cases(monkeypatch, tmp_path)
    res = auth_client.post(
        "/admin/case/cc_novichok/facts/restore",
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert (fake / "cc_novichok" / "facts.md").read_text(encoding="utf-8") == "DEFAULT facts"
    assert case_loader.load_case("cc_novichok").facts == "DEFAULT facts"


def test_restore_checklist_from_default(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _setup_fake_cases(monkeypatch, tmp_path)
    res = auth_client.post(
        "/admin/case/cc_novichok/checklist/restore",
        follow_redirects=False,
    )
    assert res.status_code == 303
    cl = case_loader.load_case("cc_novichok").checklist
    assert cl.get("needs") and cl["needs"][0].id == "N1"


def test_restore_missing_default_returns_404(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_cases = tmp_path / "cases"
    (fake_cases / "cc_novichok").mkdir(parents=True)
    (fake_cases / "cc_novichok" / "facts.md").write_text("x", encoding="utf-8")
    monkeypatch.setattr(case_loader, "_CASES_DIR", fake_cases)
    res = auth_client.post(
        "/admin/case/cc_novichok/facts/restore",
        follow_redirects=False,
    )
    assert res.status_code == 404


def test_restore_unknown_file_key_404(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _setup_fake_cases(monkeypatch, tmp_path)
    res = auth_client.post(
        "/admin/case/cc_novichok/readme/restore",
        follow_redirects=False,
    )
    assert res.status_code == 404


# ---------- checklist editor ----------


def test_checklist_save_updates_file_and_cache(
    auth_client: TestClient,
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
    res = auth_client.post(
        "/admin/case/cc_novichok/checklist/edit",
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
    auth_client: TestClient,
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
    res = auth_client.post(
        "/admin/case/cc_novichok/checklist/edit",
        data=form,
        follow_redirects=False,
    )
    assert res.status_code == 303
    import json as _json

    saved = _json.loads((fake / "cc_novichok" / "checklist.json").read_text(encoding="utf-8"))
    ids = [it["id"] for it in saved["needs"]]
    assert ids == ["N2"]


def test_checklist_add_appends_empty_item(
    auth_client: TestClient,
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
    res = auth_client.post(
        "/admin/case/cc_novichok/checklist/edit",
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
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _setup_fake_cases(monkeypatch, tmp_path)
    res = auth_client.post(
        "/admin/case/unknown/checklist/edit",
        data={"cl__needs__0__id": "x"},
        follow_redirects=False,
    )
    assert res.status_code == 404


# ---------- мультикейс: селектор и изоляция промптов ----------


def test_prompts_page_has_case_selector(auth_client: TestClient) -> None:
    res = auth_client.get("/admin/prompts")
    assert res.status_code == 200
    assert 'name="case_id"' in res.text
    assert 'value="xpv"' in res.text


def test_prompts_page_unknown_case_falls_back(auth_client: TestClient) -> None:
    res = auth_client.get("/admin/prompts?case_id=nope")
    assert res.status_code == 200  # _resolve_case_id → DEFAULT


def test_prompts_post_isolated_per_case(
    auth_client: TestClient,
    settings: Settings,
) -> None:
    from infrastructure.llm.prompt_store import PromptStore

    store = PromptStore(settings.prompts_file)
    base = store.snapshot("xpv")
    form: dict[str, str] = {
        "case_id": "xpv",
        "system_prompt": base.system_prompt,
        "sd__training": base.stage_director_prompts[Mode.TRAINING],
        "mode__training": "XPV-TRAINING-PROMPT",
    }
    res = auth_client.post("/admin/prompts", data=form, follow_redirects=False)
    assert res.status_code == 303
    assert "case_id=xpv" in res.headers["location"]

    reloaded = PromptStore(settings.prompts_file)

    assert reloaded.get_mode_prompt(Mode.TRAINING, "xpv") == "XPV-TRAINING-PROMPT"
    # cc_novichok не затронут.
    assert reloaded.get_mode_prompt(Mode.TRAINING, "cc_novichok") != "XPV-TRAINING-PROMPT"


def test_case_files_routes_work_for_new_case(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_cases = tmp_path / "cases"
    (fake_cases / "xpv").mkdir(parents=True)
    (fake_cases / "xpv" / "facts.md").write_text("XPV facts", encoding="utf-8")
    monkeypatch.setattr(case_loader, "_CASES_DIR", fake_cases)
    res = auth_client.get("/admin/case/xpv/facts")
    assert res.status_code == 200
    assert "facts.md" in res.headers.get("content-disposition", "")


# ---------- продукты: создание / переименование / YAML-экспорт ----------


@pytest.fixture
def products_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    from infrastructure.content import registry

    f = tmp_path / "products.json"
    monkeypatch.setattr(registry, "_PRODUCTS_FILE", f)
    registry.invalidate_products_cache()
    yield f
    registry.invalidate_products_cache()


def test_products_routes_require_auth(client: TestClient) -> None:
    assert client.post("/admin/products/create", data={}).status_code == 401
    assert client.post("/admin/products/xpv/rename", data={}).status_code == 401


def test_create_product_via_admin(
    auth_client: TestClient,
    products_file: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_cases = tmp_path / "cases"
    fake_cases.mkdir()
    monkeypatch.setattr(case_loader, "_CASES_DIR", fake_cases)

    res = auth_client.post(
        "/admin/products/create",
        data={"case_id": "deposit_pro", "label": "Вклад Про", "product_name": "Вклад"},
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert "case_id=deposit_pro" in res.headers["location"]
    # Скелет контента создан.
    assert (fake_cases / "deposit_pro" / "facts.md").exists()
    assert (fake_cases / "deposit_pro" / "default" / "checklist.json").exists()
    # Продукт виден в селекторе админки.
    page = auth_client.get("/admin/prompts?case_id=deposit_pro")
    assert page.status_code == 200
    assert "Вклад Про" in page.text


def test_create_product_invalid_id_400(auth_client: TestClient, products_file: Path) -> None:
    res = auth_client.post(
        "/admin/products/create",
        data={"case_id": "Bad Id", "label": "x"},
        follow_redirects=False,
    )
    assert res.status_code == 400


def test_rename_product_via_admin(auth_client: TestClient, products_file: Path) -> None:
    from infrastructure.content.registry import case_label

    res = auth_client.post(
        "/admin/products/xpv/rename",
        data={"label": "ХПВ 2.0", "product_name": "Техника ХПВ"},
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert case_label("xpv") == "ХПВ 2.0"


def test_rename_unknown_product_400(auth_client: TestClient, products_file: Path) -> None:
    res = auth_client.post(
        "/admin/products/nope/rename",
        data={"label": "x"},
        follow_redirects=False,
    )
    assert res.status_code == 400


def test_delete_product_route_requires_auth(client: TestClient) -> None:
    assert client.post("/admin/products/xpv/delete").status_code == 401


def test_delete_builtin_product_soft_delete(
    auth_client: TestClient,
    products_file: Path,
) -> None:
    from infrastructure.content.registry import all_cases, available_case_ids, is_known_case

    assert "xpv" in available_case_ids()
    assert is_known_case("xpv")

    res = auth_client.post("/admin/products/xpv/delete", follow_redirects=False)
    assert res.status_code == 303
    assert "product-deleted" in res.headers["location"]

    # Продукт скрыт из available
    assert "xpv" not in available_case_ids()
    # Но известен (soft delete — остаётся в all_cases)
    assert is_known_case("xpv")
    assert any(c.case_id == "xpv" and c.deleted for c in all_cases())


def test_delete_custom_product_hard_delete(
    auth_client: TestClient,
    products_file: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from infrastructure.content.registry import available_case_ids, is_known_case

    fake_cases = tmp_path / "cases"
    fake_cases.mkdir()
    monkeypatch.setattr(case_loader, "_CASES_DIR", fake_cases)

    # Создаём custom продукт
    auth_client.post(
        "/admin/products/create",
        data={"case_id": "deposit_pro", "label": "Вклад Про"},
        follow_redirects=False,
    )
    assert "deposit_pro" in available_case_ids()

    # Удаляем
    res = auth_client.post("/admin/products/deposit_pro/delete", follow_redirects=False)
    assert res.status_code == 303

    assert "deposit_pro" not in available_case_ids()
    assert not is_known_case("deposit_pro")  # полностью удалён


def test_delete_unknown_product_returns_400(
    auth_client: TestClient,
    products_file: Path,
) -> None:
    res = auth_client.post("/admin/products/no_such_product/delete", follow_redirects=False)
    assert res.status_code == 400


def test_export_yaml_requires_auth(client: TestClient) -> None:
    res = client.get("/admin/case/cc_novichok/export/prompts", follow_redirects=False)
    assert res.status_code == 303


def test_export_prompts_yaml_download(auth_client: TestClient) -> None:
    res = auth_client.get("/admin/case/cc_novichok/export/prompts")
    assert res.status_code == 200
    assert "yaml" in res.headers["content-type"]
    assert 'filename="prompts-cc-novichok.yaml"' in res.headers["content-disposition"]
    assert res.text.startswith("prompts:\n  map:\n")
    assert "-learning-check-prompt:" not in res.text
    assert "КРИТЕРИИ ЗАВЕРШЕНИЯ СТАДИИ (cc-novichok-learning-check):" in res.text


def test_export_variables_yaml_download(auth_client: TestClient) -> None:
    res = auth_client.get("/admin/case/xpv/export/variables")
    assert res.status_code == 200
    assert 'filename="variables-xpv.yaml"' in res.headers["content-disposition"]
    assert res.text.startswith("variables:\n  map:\n")


def test_export_unknown_kind_404(auth_client: TestClient) -> None:
    assert auth_client.get("/admin/case/cc_novichok/export/nope").status_code == 404


def test_export_unknown_case_404(auth_client: TestClient) -> None:
    assert auth_client.get("/admin/case/unknown/export/prompts").status_code == 404
