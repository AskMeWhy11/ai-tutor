"""Тесты API инлайн-редактирования фактологии (/admin/api/cases/{id}/facts).

Покрывает:
- GET: чтение текущего содержимого;
- PUT: сохранение нового содержимого;
- доступ запрещён не-администратору;
- некорректный ввод отклоняется;
- файл не существует — система ведёт себя предсказуемо;
- изменения применяются к нужному продукту (а не к соседнему).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from composition.app import create_app
from infrastructure.config import Settings
from infrastructure.content import case_loader
from infrastructure.web.security import ADMIN_COOKIE_NAME

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(tmp_path: Path, *, password: str = "s3cret") -> Settings:
    return Settings.model_validate(
        {
            "prompts_path": str(tmp_path / "prompts.json"),
            "tts_cache_dir": str(tmp_path / "tts-cache"),
            "salutespeech_enabled": False,
            "admin_username": "root",
            "admin_password": password,
            # Тесты ходят по http://, secure-cookie иначе не вернётся клиенту.
            "admin_cookie_secure": False,
        }
    )


def _setup_fake_cases(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Создать временную структуру cases/ с двумя продуктами."""
    fake_cases = tmp_path / "cases"
    for cid in ("cc_novichok", "aida"):
        case = fake_cases / cid
        case.mkdir(parents=True)
        (case / "facts.md").write_text(f"# Факты {cid}\nСодержимое.", encoding="utf-8")
    monkeypatch.setattr(case_loader, "_CASES_DIR", fake_cases)
    case_loader.invalidate_case_cache()
    return fake_cases


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return _make_settings(tmp_path)


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings=settings))


@pytest.fixture
def auth_client(client: TestClient) -> TestClient:
    """Клиент с валидной admin-сессией."""
    res = client.post(
        "/admin/login",
        data={"username": "root", "password": "s3cret"},
        follow_redirects=False,
    )
    assert res.status_code == 303, "Логин в фикстуре не прошёл"
    assert ADMIN_COOKIE_NAME in client.cookies
    return client


# ---------------------------------------------------------------------------
# GET — чтение содержимого
# ---------------------------------------------------------------------------


def test_get_facts_returns_content(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = _setup_fake_cases(monkeypatch, tmp_path)
    (fake / "cc_novichok" / "facts.md").write_text("# Заголовок\nТекст.", encoding="utf-8")

    res = auth_client.get("/admin/api/cases/cc_novichok/facts")

    assert res.status_code == 200
    assert "# Заголовок" in res.text
    assert "Текст." in res.text


def test_get_facts_file_absent_returns_empty_200(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Если facts.md не существует — 200 с пустым телом."""
    fake_cases = tmp_path / "cases"
    (fake_cases / "cc_novichok").mkdir(parents=True)
    monkeypatch.setattr(case_loader, "_CASES_DIR", fake_cases)
    case_loader.invalidate_case_cache()

    res = auth_client.get("/admin/api/cases/cc_novichok/facts")

    assert res.status_code == 200
    assert res.text == ""


def test_get_facts_unknown_case_returns_404(auth_client: TestClient) -> None:
    res = auth_client.get("/admin/api/cases/nonexistent_xyz/facts")
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# GET — доступ не-администратора
# ---------------------------------------------------------------------------


def test_get_facts_requires_auth_redirects(client: TestClient) -> None:
    """GET без сессии → редирект на логин (303)."""
    res = client.get("/admin/api/cases/cc_novichok/facts", follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"].startswith("/admin/login")


def test_get_facts_rejects_invalid_cookie(client: TestClient) -> None:
    client.cookies.set(ADMIN_COOKIE_NAME, "garbage_token")
    res = client.get("/admin/api/cases/cc_novichok/facts", follow_redirects=False)
    assert res.status_code == 303


# ---------------------------------------------------------------------------
# PUT — сохранение содержимого
# ---------------------------------------------------------------------------


def test_put_facts_saves_content_and_invalidates_cache(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = _setup_fake_cases(monkeypatch, tmp_path)
    new_text = "# Новая фактология\nОбновлённый текст."

    res = auth_client.put(
        "/admin/api/cases/cc_novichok/facts",
        content=new_text.encode("utf-8"),
        headers={"Content-Type": "text/plain; charset=utf-8"},
    )

    assert res.status_code == 204
    saved = (fake / "cc_novichok" / "facts.md").read_text(encoding="utf-8")
    assert saved == new_text
    assert "Новая фактология" in case_loader.load_case("cc_novichok").facts


def test_put_facts_applies_to_correct_product(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Изменения применяются только к указанному продукту, соседний не тронут."""
    fake = _setup_fake_cases(monkeypatch, tmp_path)
    original_aida = (fake / "aida" / "facts.md").read_text(encoding="utf-8")

    auth_client.put(
        "/admin/api/cases/cc_novichok/facts",
        content=b"# CC changed",
        headers={"Content-Type": "text/plain"},
    )

    assert (fake / "aida" / "facts.md").read_text(encoding="utf-8") == original_aida
    assert (fake / "cc_novichok" / "facts.md").read_text(encoding="utf-8") == "# CC changed"


def test_put_facts_requires_auth_returns_401(client: TestClient) -> None:
    """PUT без сессии → 401 (API-запрос, не навигация)."""
    res = client.put(
        "/admin/api/cases/cc_novichok/facts",
        content=b"# test",
        follow_redirects=False,
    )
    assert res.status_code == 401


def test_put_facts_unknown_case_returns_404(auth_client: TestClient) -> None:
    res = auth_client.put(
        "/admin/api/cases/nonexistent_xyz/facts",
        content=b"# test",
    )
    assert res.status_code == 404


def test_put_facts_creates_file_if_absent(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """PUT работает, даже если facts.md ещё не существует."""
    fake_cases = tmp_path / "cases"
    (fake_cases / "cc_novichok").mkdir(parents=True)
    monkeypatch.setattr(case_loader, "_CASES_DIR", fake_cases)
    case_loader.invalidate_case_cache()

    res = auth_client.put(
        "/admin/api/cases/cc_novichok/facts",
        content=b"# Created fresh",
        headers={"Content-Type": "text/plain"},
    )

    assert res.status_code == 204
    assert (fake_cases / "cc_novichok" / "facts.md").read_text(
        encoding="utf-8"
    ) == "# Created fresh"


# ---------------------------------------------------------------------------
# PUT — валидация входных данных
# ---------------------------------------------------------------------------


def test_put_facts_rejects_non_utf8(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_cases = tmp_path / "cases"
    (fake_cases / "cc_novichok").mkdir(parents=True)
    monkeypatch.setattr(case_loader, "_CASES_DIR", fake_cases)

    res = auth_client.put(
        "/admin/api/cases/cc_novichok/facts",
        content=b"\xff\xfe\xfa",
        headers={"Content-Type": "application/octet-stream"},
    )
    assert res.status_code == 400


def test_put_facts_rejects_too_large(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_cases = tmp_path / "cases"
    (fake_cases / "cc_novichok").mkdir(parents=True)
    monkeypatch.setattr(case_loader, "_CASES_DIR", fake_cases)

    # 'а' = 2 байта в UTF-8; 600 000 символов = ~1.2 МБ > лимит
    big = ("а" * 600_000).encode("utf-8")
    res = auth_client.put(
        "/admin/api/cases/cc_novichok/facts",
        content=big,
        headers={"Content-Type": "text/plain; charset=utf-8"},
    )
    assert res.status_code in (413, 422)


def test_put_facts_accepts_empty_content(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Явно пустое тело (стереть фактологию) должно приниматься."""
    fake = _setup_fake_cases(monkeypatch, tmp_path)

    res = auth_client.put(
        "/admin/api/cases/cc_novichok/facts",
        content=b"",
        headers={"Content-Type": "text/plain; charset=utf-8"},
    )

    assert res.status_code == 204
    assert (fake / "cc_novichok" / "facts.md").read_text(encoding="utf-8") == ""


# ---------------------------------------------------------------------------
# GET после PUT — round-trip
# ---------------------------------------------------------------------------


def test_get_facts_reflects_put(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """GET сразу после PUT возвращает только что сохранённое содержимое."""
    _setup_fake_cases(monkeypatch, tmp_path)
    payload = "# Round-trip\nПроверка записи и чтения."

    put_res = auth_client.put(
        "/admin/api/cases/cc_novichok/facts",
        content=payload.encode("utf-8"),
        headers={"Content-Type": "text/plain; charset=utf-8"},
    )
    assert put_res.status_code == 204

    get_res = auth_client.get("/admin/api/cases/cc_novichok/facts")
    assert get_res.status_code == 200
    assert get_res.text == payload
