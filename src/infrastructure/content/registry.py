"""Реестр учебных кейсов (продуктов/техник).

Два слоя:
* CASE_REGISTRY — встроенные кейсы (код);
* products.json (рядом с cases/) — пользовательский слой: созданные в админке
  продукты и переименования встроенных. Все читатели ходят через all_cases().
"""

from __future__ import annotations

import json
import logging
import re
import threading
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

__all__ = [
    "CASE_REGISTRY",
    "DEFAULT_CASE_ID",
    "CaseInfo",
    "all_cases",
    "available_case_ids",
    "case_label",
    "case_product_name",
    "create_product",
    "delete_product",
    "editable_case_ids",
    "invalidate_products_cache",
    "is_known_case",
    "is_training_only",
    "is_valid_case_slug",
    "preza_file_for",
    "rename_product",
]

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CaseInfo:
    case_id: str
    label: str
    available: bool
    preza: str = ""
    # Название темы для подстановки в {PRODUCT_NAME} промптов. Отличается от
    # label там, где в метке есть служебная часть (уровень курса и т.п.),
    # которую LLM может принять за свойство продукта. Пусто → берём label.
    product_name: str = ""
    # Продукт поддерживает только режим TRAINING (наставник, теория).
    # EXAMPLE / PRACTICE / KNOWLEDGE недоступны — нет контента кейса
    # (диалоги, чек-лист) для ролевых режимов.
    training_only: bool = False
    # Пометка удаления (soft delete): продукт скрыт из available_case_ids,
    # но id остаётся в исторических данных сессий.
    deleted: bool = False

    @property
    def prompt_name(self) -> str:
        """Название темы, которое видит LLM в {PRODUCT_NAME}."""
        return self.product_name or self.label

    @property
    def preza_file(self) -> str:
        """Имя PDF-презентации в /static/. По умолчанию <case_id>_preza.pdf."""
        return self.preza or f"{self.case_id}_preza.pdf"


DEFAULT_CASE_ID = "cc_novichok"


CASE_REGISTRY: tuple[CaseInfo, ...] = (
    # «КК_Новичок» — уровень курса, а не свойство карты: в промпт отдаём
    # чистое название продукта, иначе LLM говорит «карта для новичков».
    CaseInfo(
        "cc_novichok",
        "Кредитная карта (КК_Новичок)",
        available=True,
        preza="cc_preza.pdf",
        product_name="Кредитная карта",
    ),
    CaseInfo("xpv", "Техника ХПВ", available=True),
    CaseInfo("aida", "Техника AIDA", available=True),
    CaseInfo("spin", "SPIN-продажи", available=True),
    CaseInfo("pusk", "Техника ПУСК", available=True),
    CaseInfo("storytelling", "Сторителлинг", available=True),
)


# ----------------------------------------------------------------------
# Пользовательский слой: products.json (создание/переименование из админки)
# ----------------------------------------------------------------------

_PRODUCTS_FILE: Path = Path(__file__).resolve().parent / "cases" / "products.json"
_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")

_products_lock = threading.RLock()
# Кэш: (mtime файла, содержимое). None mtime = файла нет.
_products_cache: tuple[float | None, dict[str, Any]] | None = None


def is_valid_case_slug(case_id: str) -> bool:
    return bool(_SLUG_RE.fullmatch(case_id))


def invalidate_products_cache() -> None:
    global _products_cache
    with _products_lock:
        _products_cache = None


def _read_products_raw() -> dict[str, Any]:
    global _products_cache
    with _products_lock:
        mtime: float | None
        try:
            mtime = _PRODUCTS_FILE.stat().st_mtime
        except OSError:
            mtime = None
        if _products_cache is not None and _products_cache[0] == mtime:
            return _products_cache[1]
        data: dict[str, Any] = {}
        if mtime is not None:
            try:
                loaded = json.loads(_PRODUCTS_FILE.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data = loaded
            except (OSError, json.JSONDecodeError):
                logger.exception("Не удалось прочитать %s — игнорирую", _PRODUCTS_FILE)
        _products_cache = (mtime, data)
        return data


def _write_products_raw(data: dict[str, Any]) -> None:
    with _products_lock:
        _PRODUCTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _PRODUCTS_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(_PRODUCTS_FILE)
        invalidate_products_cache()


def all_cases() -> tuple[CaseInfo, ...]:
    """Встроенные кейсы (с учётом переименований) + пользовательские."""
    raw = _read_products_raw()
    overrides = raw.get("overrides", {})
    out: list[CaseInfo] = []
    for c in CASE_REGISTRY:
        ov = overrides.get(c.case_id)
        if isinstance(ov, dict):
            c = replace(
                c,
                label=str(ov.get("label") or c.label),
                product_name=str(ov.get("product_name") or c.product_name),
                training_only=bool(ov.get("training_only", c.training_only)),
                deleted=bool(ov.get("deleted", False)),
            )
        out.append(c)
    builtin_ids = {c.case_id for c in CASE_REGISTRY}
    for entry in raw.get("custom", []):
        if not isinstance(entry, dict):
            continue
        cid = str(entry.get("case_id", ""))
        if not is_valid_case_slug(cid) or cid in builtin_ids:
            continue
        out.append(
            CaseInfo(
                case_id=cid,
                label=str(entry.get("label") or cid),
                available=True,
                product_name=str(entry.get("product_name") or ""),
                training_only=bool(entry.get("training_only", False)),
                deleted=bool(entry.get("deleted", False)),
            )
        )
    return tuple(out)


def create_product(
    case_id: str, label: str, product_name: str = "", training_only: bool = False
) -> CaseInfo:
    """Создать пользовательский продукт. ValueError при невалидном id/дубле."""
    if not is_valid_case_slug(case_id):
        raise ValueError(
            "Неверный id: допустимы строчные латинские буквы, цифры и _, начало с буквы"
        )
    label = label.strip()
    if not label:
        raise ValueError("Название продукта не может быть пустым")
    if is_known_case(case_id):
        raise ValueError(f"Продукт с id {case_id!r} уже существует")
    with _products_lock:
        raw = dict(_read_products_raw())
        custom = [e for e in raw.get("custom", []) if isinstance(e, dict)]
        custom.append(
            {
                "case_id": case_id,
                "label": label,
                "product_name": product_name.strip(),
                "training_only": training_only,
            }
        )
        raw["custom"] = custom
        _write_products_raw(raw)
    return next(c for c in all_cases() if c.case_id == case_id)


def rename_product(
    case_id: str, label: str, product_name: str = "", training_only: bool | None = None
) -> CaseInfo:
    """Переименовать продукт (label + product_name) и/или обновить флаг training_only.
    id — технический ключ, не меняется: все связанные сущности (промпты, переменные,
    контент кейса, ключи YAML-экспорта) привязаны к id и подхватывают новое имя
    автоматически.
    """
    label = label.strip()
    if not label:
        raise ValueError("Название продукта не может быть пустым")
    if not is_known_case(case_id):
        raise ValueError(f"Неизвестный продукт {case_id!r}")
    with _products_lock:
        raw = dict(_read_products_raw())
        if any(c.case_id == case_id for c in CASE_REGISTRY):
            overrides = dict(raw.get("overrides", {}))
            ov = dict(overrides.get(case_id, {}))
            ov["label"] = label
            ov["product_name"] = product_name.strip()
            if training_only is not None:
                ov["training_only"] = training_only
            overrides[case_id] = ov
            raw["overrides"] = overrides
        else:
            raw["custom"] = [
                {
                    **e,
                    "label": label,
                    "product_name": product_name.strip(),
                    **({"training_only": training_only} if training_only is not None else {}),
                }
                if e.get("case_id") == case_id
                else e
                for e in raw.get("custom", [])
                if isinstance(e, dict)
            ]
        _write_products_raw(raw)
    return next(c for c in all_cases() if c.case_id == case_id)


def delete_product(case_id: str) -> None:
    """Удалить продукт.

    - Встроенный (из CASE_REGISTRY) -> soft delete: ставим {deleted: true} в overrides.
      Продукт исчезает из available_case_ids, но case_id остаётся в истории.
    - Пользовательский (custom) -> hard delete: убираем из списка custom.
    - Неизвестный case_id -> ValueError.
    """
    if not is_known_case(case_id):
        raise ValueError(f"Неизвестный продукт {case_id!r}")

    with _products_lock:
        raw = dict(_read_products_raw())

        if any(c.case_id == case_id for c in CASE_REGISTRY):
            # Soft delete для встроенного
            overrides = dict(raw.get("overrides", {}))
            ov = dict(overrides.get(case_id, {}))
            ov["deleted"] = True
            overrides[case_id] = ov
            raw["overrides"] = overrides
        else:
            # Hard delete для custom
            raw["custom"] = [
                e
                for e in raw.get("custom", [])
                if isinstance(e, dict) and e.get("case_id") != case_id
            ]

        _write_products_raw(raw)


# ----------------------------------------------------------------------
# Публичные lookup-функции (поверх all_cases)
# ----------------------------------------------------------------------


def available_case_ids() -> frozenset[str]:
    return frozenset(c.case_id for c in all_cases() if c.available and not c.deleted)


def editable_case_ids() -> tuple[str, ...]:
    return tuple(c.case_id for c in all_cases() if c.available and not c.deleted)


def is_known_case(case_id: str) -> bool:
    return any(c.case_id == case_id for c in all_cases())


def is_training_only(case_id: str) -> bool:
    """True, если продукт поддерживает только режим TRAINING."""
    return any(c.case_id == case_id and c.training_only for c in all_cases())


def case_label(case_id: str) -> str:
    """Человекочитаемое название кейса/продукта. Неизвестный id → сам id."""
    for c in all_cases():
        if c.case_id == case_id:
            return c.label
    return case_id


def case_product_name(case_id: str) -> str:
    """Название темы для {PRODUCT_NAME} в промптах. Неизвестный id → сам id."""
    for c in all_cases():
        if c.case_id == case_id:
            return c.prompt_name
    return case_id


def preza_file_for(case_id: str) -> str:
    """Имя PDF-презентации для кейса. Неизвестный id → презентация дефолта."""
    for c in all_cases():
        if c.case_id == case_id:
            return c.preza_file
    for c in CASE_REGISTRY:
        if c.case_id == DEFAULT_CASE_ID:
            return c.preza_file
    return "cc_preza.pdf"
