"""Загрузчик кейса из content/cases/<id>/.

Срез 2: фактология и образцовые диалоги читаются из markdown-файлов,
чек-лист — из JSON. Файлы ищем относительно корня репозитория.
Если файлы недоступны (тесты, отсутствие файлов) — fallback на встроенные
константы из cc_novichok.py / checklists/cc_novichok.py.
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from domain.types import ZONE_ORDER, Zone
from infrastructure.content.registry import DEFAULT_CASE_ID, is_known_case

__all__ = [
    "CaseContent",
    "case_dir",
    "default_case_dir",
    "facts_path",
    "invalidate_case_cache",
    "load_case",
    "read_checklist_raw",
    "read_facts_raw",
    "resolve_case_id",
    "restore_default",
    "write_checklist_raw",
    "write_facts_raw",
]


def resolve_case_id(product_id: str | None) -> str:
    """Нормализовать product_id из контекста в валидный case_id.

    Пустой/неизвестный product_id → DEFAULT_CASE_ID.
    """
    pid = (product_id or "").strip()
    if pid and is_known_case(pid):
        return pid
    return DEFAULT_CASE_ID


logger = logging.getLogger(__name__)

_CASES_DIR = Path(__file__).resolve().parent / "cases"
_DEFAULT_SUBDIR = "default"


@dataclass(frozen=True, slots=True)
class ChecklistItemDTO:
    id: str
    name: str
    criteria: str
    example_phrases: tuple[str, ...]
    keywords: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CaseContent:
    """Контент одного учебного кейса."""

    case_id: str
    facts: str
    dialogues: str
    checklist: dict[Zone, tuple[ChecklistItemDTO, ...]]


def case_dir(case_id: str) -> Path:
    """Путь к директории кейса."""
    return _CASES_DIR / case_id


def default_case_dir(case_id: str) -> Path:
    """Путь к папке с дефолтными версиями файлов кейса."""
    return case_dir(case_id) / _DEFAULT_SUBDIR


def facts_path(case_id: str) -> Path:
    """Путь к facts.md конкретного кейса."""
    return case_dir(case_id) / "facts.md"


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        logger.warning("Не удалось прочитать %s", path)
        return ""


def _read_checklist(path: Path) -> dict[Zone, tuple[ChecklistItemDTO, ...]]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.exception("Не удалось распарсить %s", path)
        return {}

    out: dict[Zone, tuple[ChecklistItemDTO, ...]] = {}
    for zone in ZONE_ORDER:
        items_raw = raw.get(zone) or []
        if not isinstance(items_raw, list):
            continue
        items: list[ChecklistItemDTO] = []
        for it in items_raw:
            if not isinstance(it, dict):
                continue
            items.append(
                ChecklistItemDTO(
                    id=str(it.get("id", "")),
                    name=str(it.get("name", "")),
                    criteria=str(it.get("criteria", "")),
                    example_phrases=tuple(str(p) for p in (it.get("example_phrases") or [])),
                    keywords=tuple(str(k).lower() for k in (it.get("keywords") or [])),
                )
            )
        out[zone] = tuple(items)
    return out


@lru_cache(maxsize=8)
def load_case(case_id: str = "cc_novichok") -> CaseContent:
    """Прочитать кейс из content/cases/<case_id>/. Кэшируется по id."""
    base = case_dir(case_id)
    facts = _read_text(base / "facts.md")
    dialogues = _read_text(base / "dialogues.md")
    checklist = _read_checklist(base / "checklist.json")
    return CaseContent(
        case_id=case_id,
        facts=facts,
        dialogues=dialogues,
        checklist=checklist,
    )


def invalidate_case_cache(case_id: str | None = None) -> None:
    """Сбросить кэш load_case. Параметр оставлен для совместимости — сбрасываем целиком."""
    load_case.cache_clear()


# ---------- Фактология: сырое чтение/запись для редактора ----------

_MAX_FACTS_BYTES: int = 1 * 1024 * 1024  # 1 МБ


def read_facts_raw(case_id: str) -> str:
    """Прочитать facts.md «как есть».

    Возвращает пустую строку, если файл не существует.
    """
    path = facts_path(case_id)
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        logger.warning("Не удалось прочитать facts.md для %s", case_id)
        return ""


def write_facts_raw(case_id: str, content: str) -> None:
    """Сохранить facts.md без обязательной загрузки файла.

    Принимает строку, проверяет размер при кодировании в UTF-8,
    атомарно записывает через временный файл.

    Raises:
        ValueError: если размер превышает допустимый.
    """
    encoded = content.encode("utf-8")
    if len(encoded) > _MAX_FACTS_BYTES:
        raise ValueError(f"Содержимое превышает допустимый размер ({_MAX_FACTS_BYTES} байт)")
    # Защита от path traversal: facts_path строится только из константы
    # _CASES_DIR и проверенного case_id (регистрация через белый список).
    path = facts_path(case_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".md.tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    invalidate_case_cache(case_id)
    logger.info("facts.md обновлён для %s (%d байт)", case_id, len(encoded))


# ---------- Чек-лист: сырое чтение/запись для редактора ----------


def read_checklist_raw(case_id: str) -> dict[str, list[dict[str, Any]]]:
    """Прочитать checklist.json «как есть» — для UI-редактора.

    Возвращает структуру по зонам ZONE_ORDER; недостающие зоны — пустые списки.
    """
    path = case_dir(case_id) / "checklist.json"
    data: dict[str, Any] = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.exception("Не удалось распарсить %s", path)
            data = {}

    out: dict[str, list[dict[str, Any]]] = {}
    for zone in ZONE_ORDER:
        items = data.get(zone) or []
        norm: list[dict[str, Any]] = []
        if isinstance(items, list):
            for it in items:
                if not isinstance(it, dict):
                    continue
                norm.append(
                    {
                        "id": str(it.get("id", "")),
                        "name": str(it.get("name", "")),
                        "criteria": str(it.get("criteria", "")),
                        "example_phrases": [str(p) for p in (it.get("example_phrases") or [])],
                        "keywords": [str(k) for k in (it.get("keywords") or [])],
                    }
                )
        out[zone] = norm
    return out


def write_checklist_raw(case_id: str, data: dict[str, list[dict[str, Any]]]) -> None:
    """Сохранить checklist.json. Структуру не валидируем строго — только нормализуем типы."""
    path = case_dir(case_id) / "checklist.json"
    payload: dict[str, list[dict[str, Any]]] = {}
    for zone in ZONE_ORDER:
        items = data.get(zone) or []
        payload[zone] = [
            {
                "id": str(it.get("id", "")),
                "name": str(it.get("name", "")),
                "criteria": str(it.get("criteria", "")),
                "example_phrases": [str(p) for p in (it.get("example_phrases") or [])],
                "keywords": [str(k) for k in (it.get("keywords") or [])],
            }
            for it in items
            if isinstance(it, dict)
        ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    invalidate_case_cache(case_id)


# ---------- Restore из default/ ----------


def restore_default(case_id: str, filename: str) -> bool:
    """Скопировать <case>/default/<filename> поверх <case>/<filename>.

    Возвращает True, если файл-дефолт существовал и был скопирован.
    """
    src = default_case_dir(case_id) / filename
    dst = case_dir(case_id) / filename
    if not src.exists():
        logger.warning("Default file missing: %s", src)
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    invalidate_case_cache(case_id)
    logger.info("Restored default for %s/%s from %s", case_id, filename, src)
    return True
