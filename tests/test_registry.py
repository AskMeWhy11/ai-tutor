from __future__ import annotations

import pytest

from infrastructure.content.registry import (
    CASE_REGISTRY,
    DEFAULT_CASE_ID,
    available_case_ids,
    is_known_case,
)


def test_default_case_is_available() -> None:
    assert DEFAULT_CASE_ID in available_case_ids()


def test_default_case_known() -> None:
    assert is_known_case(DEFAULT_CASE_ID)


def test_registry_ids_unique() -> None:
    ids = [c.case_id for c in CASE_REGISTRY]
    assert len(ids) == len(set(ids))


def test_unknown_case_rejected() -> None:
    assert not is_known_case("does_not_exist")
    assert "does_not_exist" not in available_case_ids()


def test_first_registry_entry_is_default() -> None:
    assert CASE_REGISTRY[0].case_id == DEFAULT_CASE_ID


@pytest.mark.parametrize("case_id", ["xpv", "aida", "spin", "pusk", "storytelling"])
def test_new_cases_known_and_available(case_id: str) -> None:
    assert is_known_case(case_id)
    assert case_id in available_case_ids()


def test_editable_case_ids_matches_available() -> None:
    from infrastructure.content.registry import editable_case_ids

    assert set(editable_case_ids()) == available_case_ids()
    assert editable_case_ids()[0] == DEFAULT_CASE_ID
