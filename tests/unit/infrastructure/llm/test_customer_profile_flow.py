"""Тесты: профиль клиента в PRACTICE-flow, реестр продуктов, YAML-экспорт."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from application.ports.customer_profile import CustomerProfile
from domain.states import Mode
from infrastructure.content import registry
from infrastructure.content.registry import DEFAULT_CASE_ID
from infrastructure.llm.content_render import PROFILE_DEFAULTS, apply_profile
from infrastructure.llm.prompt_store import PromptStore
from infrastructure.llm.yaml_export import export_prompts_yaml, export_variables_yaml

pytestmark = pytest.mark.unit

_PROFILE = CustomerProfile(
    client_name="Мария",
    client_age=34,
    client_gender="ж",
    client_character="осторожная",
    base_require="Планирует крупную покупку.",
)


# ---------- apply_profile / PromptStore.customer_profile ----------


def test_apply_profile_substitutes_values() -> None:
    text = "Имя: {CLIENT_NAME}, {CLIENT_AGE} лет. Хочет: {BASE_REQUIRE}"
    out = apply_profile(text, _PROFILE.as_placeholders())
    assert out == "Имя: Мария, 34 лет. Хочет: Планирует крупную покупку."


def test_apply_profile_defaults_when_missing() -> None:
    out = apply_profile("{CLIENT_NAME}/{CLIENT_CHARACTER}", None)
    assert out == f"{PROFILE_DEFAULTS['CLIENT_NAME']}/{PROFILE_DEFAULTS['CLIENT_CHARACTER']}"
    assert "{" not in out


def test_practice_prompt_includes_profile(tmp_path: Path) -> None:
    store = PromptStore(tmp_path / "prompts.json")
    # Без профиля — нейтральные дефолты, плейсхолдеры не утекают.
    text = store.get_mode_prompt(Mode.PRACTICE, DEFAULT_CASE_ID)
    assert "{CLIENT_NAME}" not in text
    assert PROFILE_DEFAULTS["CLIENT_NAME"] in text

    store.set_customer_profile(_PROFILE, DEFAULT_CASE_ID)
    text2 = store.get_mode_prompt(Mode.PRACTICE, DEFAULT_CASE_ID)
    assert "Мария" in text2
    assert "Планирует крупную покупку." in text2
    # Другие режимы профилем не трогаем.
    assert "Мария" not in store.get_mode_prompt(Mode.TRAINING, DEFAULT_CASE_ID)


def test_customer_profile_persisted(tmp_path: Path) -> None:
    path = tmp_path / "prompts.json"
    PromptStore(path).set_customer_profile(_PROFILE, "xpv")
    reloaded = PromptStore(path)
    assert reloaded.get_customer_profile("xpv") == _PROFILE.as_placeholders()
    assert reloaded.get_customer_profile(DEFAULT_CASE_ID) is None


# ---------- session_runner: генерация на старте практики ----------


class _RecordingGenerator:
    def __init__(self) -> None:
        self.calls: list[str | None] = []

    async def generate(self, *, case_id: str | None = None) -> CustomerProfile:
        self.calls.append(case_id)
        return _PROFILE


class _RecordingStore:
    def __init__(self) -> None:
        self.saved: list[tuple[str | None, dict[str, str]]] = []

    def set_customer_profile(self, profile: CustomerProfile, case_id: str | None = None) -> None:
        self.saved.append((case_id, profile.as_placeholders()))


async def test_runner_generates_profile_on_practice_start() -> None:
    import dataclasses

    from application.fsm_service import FSMService
    from application.session_runner import SessionRunner
    from domain.context import SessionContext
    from domain.states import FSMState
    from tests.fakes.in_memory_session_store import InMemorySessionStore

    gen = _RecordingGenerator()
    sink = _RecordingStore()
    runner = SessionRunner(
        fsm=FSMService(),
        store=InMemorySessionStore(),
        customer_profile_generator=gen,
        customer_profile_store=sink,
    )
    ctx = SessionContext(product_id="xpv")

    # Старт практики: история пуста → генерация.
    await runner._build_avatar_effects(FSMState.PRACTICE, ctx)
    assert gen.calls == ["xpv"]
    assert sink.saved == [("xpv", _PROFILE.as_placeholders())]

    # Продолжение практики: история непуста → повторной генерации нет.
    from domain.types import ChatMessage

    ctx2 = dataclasses.replace(ctx, dialog_history=(ChatMessage(role="assistant", text="привет"),))
    await runner._build_avatar_effects(FSMState.PRACTICE, ctx2)
    assert len(gen.calls) == 1

    # Не-PRACTICE состояния генератор не трогают.
    await runner._build_avatar_effects(FSMState.EXAMPLE, ctx)
    assert len(gen.calls) == 1


async def test_runner_survives_generator_failure() -> None:
    from application.fsm_service import FSMService
    from application.session_runner import SessionRunner
    from domain.context import SessionContext
    from domain.states import FSMState
    from tests.fakes.in_memory_session_store import InMemorySessionStore

    class _Boom:
        async def generate(self, *, case_id: str | None = None) -> CustomerProfile:
            raise RuntimeError("llm down")

    runner = SessionRunner(
        fsm=FSMService(),
        store=InMemorySessionStore(),
        customer_profile_generator=_Boom(),
        customer_profile_store=_RecordingStore(),
    )
    # Не должно бросить.
    await runner._build_avatar_effects(FSMState.PRACTICE, SessionContext(product_id="xpv"))


# ---------- реестр продуктов ----------


@pytest.fixture
def products_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    f = tmp_path / "products.json"
    monkeypatch.setattr(registry, "_PRODUCTS_FILE", f)
    registry.invalidate_products_cache()
    yield f
    registry.invalidate_products_cache()


def test_create_product_appears_everywhere(products_file: Path) -> None:
    registry.create_product("deposit_pro", "Вклад Про", "Вклад")
    assert "deposit_pro" in registry.available_case_ids()
    assert "deposit_pro" in registry.editable_case_ids()
    assert registry.case_label("deposit_pro") == "Вклад Про"
    assert registry.case_product_name("deposit_pro") == "Вклад"
    saved = json.loads(products_file.read_text(encoding="utf-8"))
    assert saved["custom"][0]["case_id"] == "deposit_pro"


def test_create_product_validation(products_file: Path) -> None:
    with pytest.raises(ValueError):
        registry.create_product("Bad-Id", "x")
    with pytest.raises(ValueError):
        registry.create_product("ok_id", "   ")
    with pytest.raises(ValueError):
        registry.create_product(DEFAULT_CASE_ID, "дубль встроенного")
    registry.create_product("ok_id", "Ок")
    with pytest.raises(ValueError):
        registry.create_product("ok_id", "дубль пользовательского")


def test_rename_builtin_and_custom(products_file: Path) -> None:
    # Встроенный: rename через overrides, id неизменен.
    registry.rename_product("xpv", "ХПВ 2.0", "Техника ХПВ")
    assert registry.case_label("xpv") == "ХПВ 2.0"
    assert registry.case_product_name("xpv") == "Техника ХПВ"
    assert "xpv" in registry.available_case_ids()

    # Пользовательский.
    registry.create_product("deposit_pro", "Вклад Про")
    registry.rename_product("deposit_pro", "Вклад Про Макс", "Вклад")
    assert registry.case_label("deposit_pro") == "Вклад Про Макс"

    with pytest.raises(ValueError):
        registry.rename_product("nope", "x")


def test_rename_cascades_to_prompt_name_variable(products_file: Path, tmp_path: Path) -> None:
    """{PRODUCT_NAME} и prompts_map подхватывают новое имя без пересохранений."""
    from infrastructure.llm.default_prompts import prompts_map
    from infrastructure.llm.variables import resolve_variable

    registry.rename_product("xpv", "ХПВ переименованная", "Новое имя ХПВ")
    assert resolve_variable("product-name", "xpv") == "Новое имя ХПВ"
    # Ключи prompts_map стабильны (id не меняется).
    assert "xpv-learning-transcription-prompt" in prompts_map()


# ---------- YAML-экспорт ----------


def test_export_prompts_yaml_reference_structure(tmp_path: Path) -> None:
    store = PromptStore(tmp_path / "prompts.json")
    out = export_prompts_yaml(store, "cc_novichok")
    lines = out.split("\n")
    assert lines[0] == "prompts:"
    assert lines[1] == "  map:"
    # Ключи — kebab, 4 пробела, block scalar.
    assert "    cc-novichok-learning-transcription-prompt: |" in out
    assert "    cc-novichok-employee-transcription-prompt: |" in out
    assert "    cc-novichok-create-customer-profile-system-prompt: |" in out
    # Контент блоков — с отступом 6.
    idx = lines.index("    cc-novichok-learning-transcription-prompt: |")
    assert lines[idx + 1].startswith("      ")


def test_export_prompts_yaml_reflects_edits(tmp_path: Path) -> None:
    store = PromptStore(tmp_path / "prompts.json")
    snap = store.snapshot("xpv")
    store.replace_all(
        system_prompt=snap.system_prompt,
        templates=snap.templates,
        quiz_prompt="EDITED QUIZ TEXT",
        case_id="xpv",
    )
    out = export_prompts_yaml(store, "xpv")
    assert "    xpv-learning-quiz-transcription-prompt: |" in out
    assert "      EDITED QUIZ TEXT" in out


def test_export_variables_yaml_reference_structure() -> None:
    out = export_variables_yaml(DEFAULT_CASE_ID)
    lines = out.split("\n")
    assert lines[0] == "variables:"
    assert lines[1] == "  map:"
    # kebab-ключи, значения — однострочные JSON-строки.
    assert any(line.startswith('    product-details: "') for line in lines)
    assert any(line.startswith('    product-name: "') for line in lines)
    # Многострочный контент упакован в \n, а не в реальные переводы строк.
    details_line = next(line for line in lines if line.startswith("    product-details:"))
    assert "\\n" in details_line or len(details_line) < 200
