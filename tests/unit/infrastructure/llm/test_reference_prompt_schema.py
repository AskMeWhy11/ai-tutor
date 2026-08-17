"""Тесты эталонной структуры промптов: prompts_map, переменные, миграция v8."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from application.ports.customer_profile import CustomerProfile
from domain.states import Mode
from infrastructure.content.registry import DEFAULT_CASE_ID, editable_case_ids
from infrastructure.llm.content_render import LEGACY_PLACEHOLDERS, PLACEHOLDERS, render_prompt
from infrastructure.llm.default_prompts import (
    default_customer_profile_system_prompt,
    default_customer_profile_user_prompt,
    prompts_map,
)
from infrastructure.llm.prompt_store import PromptStore
from infrastructure.llm.stub_customer_profile import StubCustomerProfileGenerator
from infrastructure.llm.variables import VARIABLES_MAP, placeholder_name, resolve_variable

pytestmark = pytest.mark.unit

_PURPOSES = (
    "learning-transcription",
    "learning-quiz-transcription",
    "learning-check",
    "client-transcription",
    "employee-transcription",
    "mentor-transcription",
    "create-customer-profile-system",
    "create-customer-profile-user",
)


# ---------- prompts_map: эталонная структура ключей ----------


def test_prompts_map_has_all_keys_for_all_cases() -> None:
    pm = prompts_map()
    for cid in editable_case_ids():
        slug = cid.replace("_", "-")
        for purpose in _PURPOSES:
            key = f"{slug}-{purpose}-prompt"
            assert key in pm, key
            assert pm[key].strip()


def test_prompts_map_keys_follow_reference_grammar() -> None:
    # <kebab>-prompt, без underscore и заглавных
    for key in prompts_map():
        assert key.endswith("-prompt")
        assert "_" not in key
        assert key == key.lower()


def test_prompts_use_only_reference_placeholders() -> None:
    import re

    allowed = set(PLACEHOLDERS)
    for key, text in prompts_map().items():
        found = set(re.findall(r"\{([A-Z][A-Z_]*)\}", text))
        assert found <= allowed, f"{key}: неизвестные плейсхолдеры {found - allowed}"


# ---------- variables: эталонный реестр ----------


def test_variable_keys_are_kebab_case() -> None:
    for key in VARIABLES_MAP:
        assert key == key.lower()
        assert "_" not in key


def test_placeholder_name_mapping() -> None:
    assert placeholder_name("product-details") == "PRODUCT_DETAILS"
    assert placeholder_name("real-dialogues") == "REAL_DIALOGUES"


def test_resolve_variable_unknown_raises() -> None:
    with pytest.raises(KeyError):
        resolve_variable("nope", DEFAULT_CASE_ID)


def test_render_prompt_substitutes_reference_placeholders() -> None:
    out = render_prompt("Имя: {PRODUCT_NAME}\nФакты: {PRODUCT_DETAILS}", DEFAULT_CASE_ID)
    assert "{PRODUCT_NAME}" not in out
    assert "{PRODUCT_DETAILS}" not in out


def test_render_prompt_supports_legacy_placeholders() -> None:
    legacy = render_prompt("«{PRODUCT}»: {FACTS} / {DIALOGUES}", DEFAULT_CASE_ID)
    modern = render_prompt(
        "«{PRODUCT_NAME}»: {PRODUCT_DETAILS} / {REAL_DIALOGUES}", DEFAULT_CASE_ID
    )
    assert legacy == modern


# ---------- prompt_store: миграция v7 → v8 ----------


def test_store_migrates_legacy_placeholders(tmp_path: Path) -> None:
    payload = {
        "version": 7,
        "system_prompt": "Продукт {PRODUCT}",
        "templates": {},
        "cases": {
            DEFAULT_CASE_ID: {
                "mode_prompts": {
                    "training": "T {FACTS}",
                    "example": "E {DIALOGUES}",
                    "practice": "P {FACTS} {DIALOGUES}",
                    "knowledge": "K {PRODUCT}",
                },
                "quiz_prompt": "Q {FACTS}",
                "stage_director_prompt": "S {PRODUCT}",
            }
        },
    }
    path = tmp_path / "prompts.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    store = PromptStore(path)
    snap = store.snapshot(DEFAULT_CASE_ID)
    assert snap.mode_prompts[Mode.TRAINING] == "T {PRODUCT_DETAILS}"
    assert snap.mode_prompts[Mode.EXAMPLE] == "E {REAL_DIALOGUES}"
    assert snap.mode_prompts[Mode.KNOWLEDGE] == "K {PRODUCT_NAME}"
    assert snap.quiz_prompt == "Q {PRODUCT_DETAILS}"
    assert snap.stage_director_prompt == "S {PRODUCT_NAME}"
    assert snap.system_prompt == "Продукт {PRODUCT_NAME}"

    # Файл переписан в v8 — legacy-плейсхолдеров больше нет.
    raw = path.read_text(encoding="utf-8")
    assert raw and json.loads(raw)["version"] == 8
    for old in LEGACY_PLACEHOLDERS:
        assert "{" + old + "}" not in raw


# ---------- customer profile ----------


def test_default_profile_prompts_present_in_snapshot(tmp_path: Path) -> None:
    store = PromptStore(tmp_path / "prompts.json")
    snap = store.snapshot(DEFAULT_CASE_ID)
    assert "JSON" in snap.customer_profile_system_prompt
    assert snap.customer_profile_user_prompt.strip()


def test_profile_prompts_roundtrip_and_restore(tmp_path: Path) -> None:
    path = tmp_path / "prompts.json"
    store = PromptStore(path)
    snap = store.snapshot(DEFAULT_CASE_ID)
    store.replace_all(
        system_prompt=snap.system_prompt,
        templates=snap.templates,
        customer_profile_system_prompt="SYS-EDITED",
        customer_profile_user_prompt="USER-EDITED",
        case_id=DEFAULT_CASE_ID,
    )
    reloaded = PromptStore(path)
    system, user = reloaded.get_customer_profile_prompts(DEFAULT_CASE_ID)
    assert system == "SYS-EDITED"
    assert user == "USER-EDITED"

    reloaded.restore_customer_profile_prompts(DEFAULT_CASE_ID)
    system2, _ = reloaded.get_customer_profile_prompts(DEFAULT_CASE_ID)
    assert system2 == render_prompt(
        default_customer_profile_system_prompt(DEFAULT_CASE_ID), DEFAULT_CASE_ID
    )


def test_profile_prompts_rendered_without_placeholders(tmp_path: Path) -> None:
    store = PromptStore(tmp_path / "prompts.json")
    system, user = store.get_customer_profile_prompts(DEFAULT_CASE_ID)
    assert "{PRODUCT_NAME}" not in system
    assert "{PRODUCT_DETAILS}" not in system
    assert "{PRODUCT_NAME}" not in user
    # JSON-литералы формата ответа остаются нетронутыми
    assert "client_name" in system


def test_default_profile_user_prompt_nonempty_for_all_cases() -> None:
    for cid in editable_case_ids():
        assert default_customer_profile_user_prompt(cid).strip()


async def test_stub_profile_generator_returns_valid_profiles() -> None:
    gen = StubCustomerProfileGenerator()
    seen: list[CustomerProfile] = [await gen.generate(case_id=DEFAULT_CASE_ID) for _ in range(4)]
    for p in seen:
        assert p.client_name and p.base_require
        assert 18 <= p.client_age <= 99
        ph = p.as_placeholders()
        assert set(ph) == {
            "CLIENT_NAME",
            "CLIENT_AGE",
            "CLIENT_GENDER",
            "CLIENT_CHARACTER",
            "BASE_REQUIRE",
        }
    # набор циклический — профили меняются
    assert len({p.client_name for p in seen}) > 1
