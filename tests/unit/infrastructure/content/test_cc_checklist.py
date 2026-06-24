"""Smoke-тесты структурированного чек-листа КК_Новичок."""

from __future__ import annotations

from domain.types import ZONE_ORDER
from infrastructure.content.checklists.cc_novichok import (
    CHECKLIST,
    keywords_for_zone,
    zone_label,
)


def test_checklist_has_all_canonical_zones() -> None:
    assert tuple(CHECKLIST.keys()) == ZONE_ORDER


def test_each_zone_has_at_least_one_item() -> None:
    for zone, items in CHECKLIST.items():
        assert items, f"zone {zone} пустая"


def test_item_ids_are_unique_within_zone() -> None:
    for zone, items in CHECKLIST.items():
        ids = [it.id for it in items]
        assert len(ids) == len(set(ids)), f"дубли id в зоне {zone}: {ids}"


def test_keywords_for_zone_returns_lowercase_unique() -> None:
    for zone in ZONE_ORDER:
        kws = keywords_for_zone(zone)
        assert all(kw == kw.lower() for kw in kws)
        assert len(kws) == len(set(kws))


def test_zone_label_returns_human_readable() -> None:
    assert zone_label("needs") != "needs"
    assert zone_label("pitch") != "pitch"
    assert zone_label("conditions") != "conditions"
