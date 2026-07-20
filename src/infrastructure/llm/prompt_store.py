"""Хранилище редактируемых промпт-шаблонов и системных промптов режимов.

Структура промптов:
- Глобальные (общие для всех кейсов): system_prompt, templates (служебные
  реплики FSM).
- Per-case (свои у каждого продукта): mode_prompts (TRAINING/EXAMPLE/
  PRACTICE/KNOWLEDGE), quiz_prompt, stage_director_prompt.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from domain.states import FSMState, Mode
from infrastructure.content.registry import DEFAULT_CASE_ID, editable_case_ids
from infrastructure.llm.content_render import render_prompt
from infrastructure.llm.default_prompts import (
    default_mode_prompts,
    default_quiz_prompt,
    default_stage_director_prompt,
)

__all__ = [
    "DYNAMIC_STATES",
    "EDITABLE_STATES",
    "PromptSnapshot",
    "PromptStore",
    "default_templates",
]

logger = logging.getLogger(__name__)

DYNAMIC_STATES: Final[frozenset[FSMState]] = frozenset(
    {
        FSMState.TRAINING,
        FSMState.TRAINING_QUIZ,
        FSMState.TRAINING_EXPLAIN,
        FSMState.EXAMPLE,
        FSMState.PRACTICE,
        FSMState.PRACTICE_PARTIAL,
        FSMState.KNOWLEDGE,
    }
)

EDITABLE_STATES: Final[tuple[FSMState, ...]] = tuple(s for s in FSMState if s not in DYNAMIC_STATES)

# v6: mode_prompts/quiz_prompt хранятся как шаблоны с плейсхолдерами
#     {FACTS}/{DIALOGUES}; контент подставляется при чтении (render_prompt).
# v7: stage_director_prompt переехал из глобального поля в per-case bundle
#     (свой вариант для продуктов-техник продаж и для cc_novichok).
_SCHEMA_VERSION: Final[int] = 7


def default_templates() -> dict[FSMState, str]:
    return {
        FSMState.INIT: "Запускаю тренажёр...",
        FSMState.RESUME_PROMPT: (
            "Я нашёл твою прошлую сессию. Продолжим с того же места или начнём заново?"
        ),
        FSMState.MENU: "Выбери продукт, по которому хочешь потренироваться, и введи своё имя.",
        FSMState.WELCOME: "",
        FSMState.TRAINING_DONE: (
            "Отлично, теоретическую часть прошли. Теперь покажу, "
            "как это работает в живом диалоге с клиентом."
        ),
        FSMState.SKIP_WARNING_1: (
            "Ты ещё не проходил «Обучение». Пример будет понятнее, "
            "если сначала разобрать теорию. Точно хочешь пропустить?"
        ),
        FSMState.SKIP_WARNING_2: (
            "Ты ещё не проходил «Обучение». В практике без теории "
            "будет сложно. Точно хочешь пропустить?"
        ),
        FSMState.EXAMPLE_DONE: (
            "Образцовый диалог посмотрели. Готов попробовать сам? Я буду играть за клиента."
        ),
        FSMState.PRACTICE_EVAL: "Анализирую твой ответ...",
        FSMState.PRACTICE_SUCCESS: "Практику прошли — без слабых зон. Отличная работа!",
        FSMState.KNOWLEDGE_DONE: (
            "Слабые зоны подтянули. Предлагаю ещё раз пройти практику — "
            "теперь должно пойти увереннее."
        ),
        FSMState.FINISH: ("Обучение завершено. Молодец! Возвращайся, когда понадобится повторить."),
    }


@dataclass(frozen=True, slots=True)
class PromptSnapshot:
    version: int
    system_prompt: str
    templates: dict[FSMState, str] = field(default_factory=dict)
    mode_prompts: dict[Mode, str] = field(default_factory=dict)
    quiz_prompt: str = ""
    stage_director_prompt: str = ""
    case_id: str = DEFAULT_CASE_ID


@dataclass(slots=True)
class _CaseBundle:
    mode_prompts: dict[Mode, str]
    quiz_prompt: str
    stage_director_prompt: str


class PromptStore:
    def __init__(self, path: Path, *, system_prompt_default: str = "") -> None:
        self._path = path
        self._lock = threading.RLock()
        self._system_prompt: str = system_prompt_default
        self._templates: dict[FSMState, str] = {}
        self._cases: dict[str, _CaseBundle] = {}
        self._loaded = False

    # ----- helpers -----

    @staticmethod
    def _resolve_case(case_id: str | None) -> str:
        return case_id if case_id else DEFAULT_CASE_ID

    def _bundle(self, case_id: str | None) -> _CaseBundle:
        cid = self._resolve_case(case_id)
        bundle = self._cases.get(cid)
        if bundle is None:
            bundle = _CaseBundle(
                mode_prompts=default_mode_prompts(cid),
                quiz_prompt=default_quiz_prompt(cid),
                stage_director_prompt=default_stage_director_prompt(cid),
            )
            self._cases[cid] = bundle
        return bundle

    # ----- публичный API: глобальные -----

    def get_template(self, state: FSMState) -> str:
        self._ensure_loaded()
        with self._lock:
            return self._templates.get(state, "")

    def set_template(self, state: FSMState, text: str) -> None:
        if state in DYNAMIC_STATES:
            raise ValueError(f"Состояние {state.value} динамическое — редактирование запрещено")
        self._ensure_loaded()
        with self._lock:
            self._templates[state] = text
            self._flush_unlocked()

    def get_stage_director_prompt(self, case_id: str | None = None) -> str:
        self._ensure_loaded()
        with self._lock:
            template = self._bundle(case_id).stage_director_prompt
        return render_prompt(template, case_id)

    # ----- публичный API: per-case -----

    def get_mode_prompt(self, mode: Mode, case_id: str | None = None) -> str:
        self._ensure_loaded()
        with self._lock:
            template = self._bundle(case_id).mode_prompts.get(mode, "")
        return render_prompt(template, case_id)

    def get_quiz_prompt(self, case_id: str | None = None) -> str:
        self._ensure_loaded()
        with self._lock:
            template = self._bundle(case_id).quiz_prompt
        return render_prompt(template, case_id)

    def replace_all(
        self,
        system_prompt: str,
        templates: dict[FSMState, str],
        mode_prompts: dict[Mode, str] | None = None,
        quiz_prompt: str | None = None,
        stage_director_prompt: str | None = None,
        case_id: str | None = None,
    ) -> None:
        """Сохранить глобальные промпты + per-case (mode/quiz) для case_id."""
        self._ensure_loaded()
        with self._lock:
            self._system_prompt = system_prompt
            self._templates = {s: t for s, t in templates.items() if s not in DYNAMIC_STATES}
            has_overrides = (
                mode_prompts is not None
                or quiz_prompt is not None
                or stage_director_prompt is not None
            )
            if has_overrides:
                bundle = self._bundle(case_id)
                if mode_prompts is not None:
                    bundle.mode_prompts = {
                        m: t for m, t in mode_prompts.items() if isinstance(m, Mode)
                    }
                if quiz_prompt is not None:
                    bundle.quiz_prompt = quiz_prompt
                if stage_director_prompt is not None:
                    bundle.stage_director_prompt = stage_director_prompt
            self._flush_unlocked()

    def restore_mode_prompt(self, mode: Mode, case_id: str | None = None) -> str:
        """Сбросить промпт режима к дефолту (фактология из cases/<id>/)."""
        self._ensure_loaded()
        with self._lock:
            cid = self._resolve_case(case_id)
            text = default_mode_prompts(cid)[mode]
            self._bundle(cid).mode_prompts[mode] = text
            self._flush_unlocked()
            return text

    def restore_quiz_prompt(self, case_id: str | None = None) -> str:
        """Сбросить квиз-промпт к дефолту."""
        self._ensure_loaded()
        with self._lock:
            cid = self._resolve_case(case_id)
            text = default_quiz_prompt(cid)
            self._bundle(cid).quiz_prompt = text
            self._flush_unlocked()
            return text

    def snapshot(self, case_id: str | None = None) -> PromptSnapshot:
        self._ensure_loaded()
        with self._lock:
            cid = self._resolve_case(case_id)
            bundle = self._bundle(cid)
            tpls = {s: self._templates.get(s, "") for s in EDITABLE_STATES}
            modes = {m: bundle.mode_prompts.get(m, "") for m in Mode}
            return PromptSnapshot(
                version=_SCHEMA_VERSION,
                system_prompt=self._system_prompt,
                templates=tpls,
                mode_prompts=modes,
                quiz_prompt=bundle.quiz_prompt,
                stage_director_prompt=bundle.stage_director_prompt,
                case_id=cid,
            )

    # ----- внутреннее -----

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            if self._path.exists():
                self._load_unlocked()
            else:
                self._init_defaults_unlocked()
                self._flush_unlocked()
            self._loaded = True

    def _init_defaults_unlocked(self) -> None:
        self._templates = default_templates()
        self._cases = {
            cid: _CaseBundle(
                mode_prompts=default_mode_prompts(cid),
                quiz_prompt=default_quiz_prompt(cid),
                stage_director_prompt=default_stage_director_prompt(cid),
            )
            for cid in editable_case_ids()
        }

    def _load_unlocked(self) -> None:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.exception("Не удалось прочитать %s, использую дефолты", self._path)
            self._init_defaults_unlocked()
            return

        version = raw.get("version", _SCHEMA_VERSION)
        if version != _SCHEMA_VERSION:
            logger.warning(
                "Версия %s файла промптов != %s, мигрирую/мерджу с дефолтами",
                version,
                _SCHEMA_VERSION,
            )
        # v<6: mode/quiz хранили отрендеренный контент. Сбрасываем их к
        # шаблонам с плейсхолдерами — контент теперь подставляется динамически.
        drop_case_prompts = version < 6
        # v<7: stage_director_prompt был глобальным полем — если он был
        # реально изменён администратором, сохраняем его как per-case
        # значение ТОЛЬКО для DEFAULT_CASE_ID (остальные кейсы получают
        # свежий per-case дефолт, включая новый вариант для техник продаж).
        legacy_sd_raw = raw.get("stage_director_prompt") if version < 7 else None
        legacy_sd = (
            legacy_sd_raw if isinstance(legacy_sd_raw, str) and legacy_sd_raw.strip() else None
        )

        self._system_prompt = str(raw.get("system_prompt", ""))

        # --- глобальные templates ---
        loaded_tpls = raw.get("templates", {}) or {}
        merged_tpls = default_templates()
        if isinstance(loaded_tpls, dict):
            for key, value in loaded_tpls.items():
                try:
                    state = FSMState(key)
                except ValueError:
                    logger.warning("Неизвестный state %r — игнорирую", key)
                    continue
                if state in DYNAMIC_STATES:
                    continue
                merged_tpls[state] = str(value)
        self._templates = merged_tpls

        # --- per-case bundles ---
        cases_raw = raw.get("cases")
        if drop_case_prompts:
            self._cases = {
                cid: _CaseBundle(
                    mode_prompts=default_mode_prompts(cid),
                    quiz_prompt=default_quiz_prompt(cid),
                    stage_director_prompt=(
                        legacy_sd
                        if legacy_sd is not None and cid == DEFAULT_CASE_ID
                        else default_stage_director_prompt(cid)
                    ),
                )
                for cid in editable_case_ids()
            }
            self._flush_unlocked()
        elif isinstance(cases_raw, dict) and cases_raw:
            self._cases = self._load_cases_unlocked(cases_raw)
            if legacy_sd is not None and DEFAULT_CASE_ID in self._cases:
                self._cases[DEFAULT_CASE_ID].stage_director_prompt = legacy_sd
                self._flush_unlocked()
        else:
            # Миграция v4→v5: глобальные mode_prompts/quiz_prompt → DEFAULT_CASE_ID.
            self._cases = self._migrate_legacy_unlocked(raw, legacy_sd)

    def _load_cases_unlocked(self, cases_raw: dict[str, Any]) -> dict[str, _CaseBundle]:
        out: dict[str, _CaseBundle] = {}
        for cid in editable_case_ids():
            entry = cases_raw.get(cid)
            out[cid] = self._parse_bundle(cid, entry if isinstance(entry, dict) else None)
        # Кейсы из файла, которых нет в реестре, — сохраняем как есть.
        for cid, entry in cases_raw.items():
            if cid not in out and isinstance(entry, dict):
                out[cid] = self._parse_bundle(cid, entry)
        return out

    def _migrate_legacy_unlocked(
        self, raw: dict[str, Any], legacy_sd: str | None = None
    ) -> dict[str, _CaseBundle]:
        legacy_modes_raw = raw.get("mode_prompts", {}) or {}
        legacy_modes = self._parse_modes(
            DEFAULT_CASE_ID, legacy_modes_raw if isinstance(legacy_modes_raw, dict) else {}
        )
        legacy_quiz_raw = raw.get("quiz_prompt")
        legacy_quiz = (
            legacy_quiz_raw
            if isinstance(legacy_quiz_raw, str) and legacy_quiz_raw.strip()
            else default_quiz_prompt(DEFAULT_CASE_ID)
        )
        legacy_stage_director = legacy_sd or default_stage_director_prompt(DEFAULT_CASE_ID)
        out: dict[str, _CaseBundle] = {}
        for cid in editable_case_ids():
            if cid == DEFAULT_CASE_ID:
                out[cid] = _CaseBundle(
                    mode_prompts=legacy_modes,
                    quiz_prompt=legacy_quiz,
                    stage_director_prompt=legacy_stage_director,
                )
            else:
                out[cid] = _CaseBundle(
                    quiz_prompt=default_quiz_prompt(cid),
                    mode_prompts=default_mode_prompts(cid),
                    stage_director_prompt=default_stage_director_prompt(cid),
                )
        return out

    def _parse_bundle(self, case_id: str, entry: dict[str, Any] | None) -> _CaseBundle:
        if entry is None:
            return _CaseBundle(
                mode_prompts=default_mode_prompts(case_id),
                quiz_prompt=default_quiz_prompt(case_id),
                stage_director_prompt=default_stage_director_prompt(case_id),
            )
        modes_raw = entry.get("mode_prompts", {}) or {}
        modes = self._parse_modes(case_id, modes_raw if isinstance(modes_raw, dict) else {})
        quiz_raw = entry.get("quiz_prompt")
        quiz = (
            quiz_raw
            if isinstance(quiz_raw, str) and quiz_raw.strip()
            else default_quiz_prompt(case_id)
        )
        sd_raw = entry.get("stage_director_prompt")
        stage_director = (
            sd_raw
            if isinstance(sd_raw, str) and sd_raw.strip()
            else default_stage_director_prompt(case_id)
        )
        return _CaseBundle(
            mode_prompts=modes,
            quiz_prompt=quiz,
            stage_director_prompt=stage_director,
        )

    @staticmethod
    def _parse_modes(case_id: str, loaded_modes: dict[str, Any]) -> dict[Mode, str]:
        merged = default_mode_prompts(case_id)
        for key, value in loaded_modes.items():
            try:
                mode = Mode(key)
            except ValueError:
                logger.warning("Неизвестный mode %r — игнорирую", key)
                continue
            text = str(value)
            if text.strip():
                merged[mode] = text
        return merged

    def _flush_unlocked(self) -> None:
        payload = {
            "version": _SCHEMA_VERSION,
            "system_prompt": self._system_prompt,
            "templates": {s.value: self._templates.get(s, "") for s in EDITABLE_STATES},
            "cases": {
                cid: {
                    "mode_prompts": {m.value: b.mode_prompts.get(m, "") for m in Mode},
                    "quiz_prompt": b.quiz_prompt,
                    "stage_director_prompt": b.stage_director_prompt,
                }
                for cid, b in self._cases.items()
            },
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._path)
