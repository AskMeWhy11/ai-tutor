"""Реестр учебных кейсов (продуктов/техник)."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "CASE_REGISTRY",
    "DEFAULT_CASE_ID",
    "CaseInfo",
    "available_case_ids",
    "case_label",
    "editable_case_ids",
    "is_known_case",
    "preza_file_for",
]


@dataclass(frozen=True, slots=True)
class CaseInfo:
    case_id: str
    label: str
    available: bool
    preza: str = ""

    @property
    def preza_file(self) -> str:
        """Имя PDF-презентации в /static/. По умолчанию <case_id>_preza.pdf."""
        return self.preza or f"{self.case_id}_preza.pdf"


DEFAULT_CASE_ID = "cc_novichok"


CASE_REGISTRY: tuple[CaseInfo, ...] = (
    CaseInfo("cc_novichok", "Кредитная карта (КК_Новичок)", available=True, preza="cc_preza.pdf"),
    CaseInfo("xpv", "Техника ХПВ", available=True),
    CaseInfo("aida", "Техника AIDA", available=True),
    CaseInfo("spin", "SPIN-продажи", available=True),
    CaseInfo("pusk", "Техника ПУСК", available=True),
    CaseInfo("storytelling", "Сторителлинг", available=True),
)


def available_case_ids() -> frozenset[str]:
    return frozenset(c.case_id for c in CASE_REGISTRY if c.available)


def editable_case_ids() -> tuple[str, ...]:
    return tuple(c.case_id for c in CASE_REGISTRY if c.available)


def is_known_case(case_id: str) -> bool:
    return any(c.case_id == case_id for c in CASE_REGISTRY)


def case_label(case_id: str) -> str:
    """Человекочитаемое название кейса/продукта. Неизвестный id → сам id."""
    for c in CASE_REGISTRY:
        if c.case_id == case_id:
            return c.label
    return case_id


def preza_file_for(case_id: str) -> str:
    """Имя PDF-презентации для кейса. Неизвестный id → презентация дефолта."""
    for c in CASE_REGISTRY:
        if c.case_id == case_id:
            return c.preza_file
    for c in CASE_REGISTRY:
        if c.case_id == DEFAULT_CASE_ID:
            return c.preza_file
    return "cc_preza.pdf"
