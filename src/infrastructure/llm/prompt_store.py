"""Хранилище редактируемых промпт-шаблонов и системных промптов режимов."""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from domain.states import FSMState, Mode
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

# v4: добавили stage_director_prompt.
_SCHEMA_VERSION: Final[int] = 4


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


class PromptStore:
    def __init__(self, path: Path, *, system_prompt_default: str = "") -> None:
        self._path = path
        self._lock = threading.RLock()
        self._system_prompt: str = system_prompt_default
        self._templates: dict[FSMState, str] = {}
        self._mode_prompts: dict[Mode, str] = {}
        self._quiz_prompt: str = ""
        self._stage_director_prompt: str = ""
        self._loaded = False

    # ----- публичный API -----

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

    def get_mode_prompt(self, mode: Mode) -> str:
        self._ensure_loaded()
        with self._lock:
            return self._mode_prompts.get(mode, "")

    def get_quiz_prompt(self) -> str:
        self._ensure_loaded()
        with self._lock:
            return self._quiz_prompt

    def get_stage_director_prompt(self) -> str:
        self._ensure_loaded()
        with self._lock:
            return self._stage_director_prompt

    def replace_all(
        self,
        system_prompt: str,
        templates: dict[FSMState, str],
        mode_prompts: dict[Mode, str] | None = None,
        quiz_prompt: str | None = None,
        stage_director_prompt: str | None = None,
    ) -> None:
        self._ensure_loaded()
        with self._lock:
            self._system_prompt = system_prompt
            self._templates = {s: t for s, t in templates.items() if s not in DYNAMIC_STATES}
            if mode_prompts is not None:
                self._mode_prompts = {m: t for m, t in mode_prompts.items() if isinstance(m, Mode)}
            if quiz_prompt is not None:
                self._quiz_prompt = quiz_prompt
            if stage_director_prompt is not None:
                self._stage_director_prompt = stage_director_prompt
            self._flush_unlocked()

    def snapshot(self) -> PromptSnapshot:
        self._ensure_loaded()
        with self._lock:
            tpls = {s: self._templates.get(s, "") for s in EDITABLE_STATES}
            modes = {m: self._mode_prompts.get(m, "") for m in Mode}
            return PromptSnapshot(
                version=_SCHEMA_VERSION,
                system_prompt=self._system_prompt,
                templates=tpls,
                mode_prompts=modes,
                quiz_prompt=self._quiz_prompt,
                stage_director_prompt=self._stage_director_prompt,
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
                self._templates = default_templates()
                self._mode_prompts = default_mode_prompts()
                self._quiz_prompt = default_quiz_prompt()
                self._stage_director_prompt = default_stage_director_prompt()
                self._flush_unlocked()
            self._loaded = True

    def _load_unlocked(self) -> None:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.exception("Не удалось прочитать %s, использую дефолты", self._path)
            self._templates = default_templates()
            self._mode_prompts = default_mode_prompts()
            self._quiz_prompt = default_quiz_prompt()
            self._stage_director_prompt = default_stage_director_prompt()
            return

        version = raw.get("version", _SCHEMA_VERSION)
        if version != _SCHEMA_VERSION:
            logger.warning(
                "Версия %s файла промптов != %s, мерджу с дефолтами",
                version,
                _SCHEMA_VERSION,
            )

        self._system_prompt = str(raw.get("system_prompt", ""))

        loaded_tpls = raw.get("templates", {}) or {}
        merged_tpls = default_templates()
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

        loaded_modes = raw.get("mode_prompts", {}) or {}
        merged_modes = default_mode_prompts()
        for key, value in loaded_modes.items():
            try:
                mode = Mode(key)
            except ValueError:
                logger.warning("Неизвестный mode %r — игнорирую", key)
                continue
            text = str(value).strip()
            if text:
                merged_modes[mode] = str(value)
        self._mode_prompts = merged_modes

        loaded_quiz = raw.get("quiz_prompt")
        self._quiz_prompt = (
            loaded_quiz
            if isinstance(loaded_quiz, str) and loaded_quiz.strip()
            else default_quiz_prompt()
        )

        loaded_sd = raw.get("stage_director_prompt")
        self._stage_director_prompt = (
            loaded_sd
            if isinstance(loaded_sd, str) and loaded_sd.strip()
            else default_stage_director_prompt()
        )

    def _flush_unlocked(self) -> None:
        payload = {
            "version": _SCHEMA_VERSION,
            "system_prompt": self._system_prompt,
            "templates": {s.value: self._templates.get(s, "") for s in EDITABLE_STATES},
            "mode_prompts": {m.value: self._mode_prompts.get(m, "") for m in Mode},
            "quiz_prompt": self._quiz_prompt,
            "stage_director_prompt": self._stage_director_prompt,
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._path)
