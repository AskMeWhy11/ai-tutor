"""Команды, поступающие в FSMService от UI/контроллера."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class StartSession: ...


@dataclass(frozen=True)
class ResumeChoice:
    resume: bool


@dataclass(frozen=True)
class StartTraining:
    employee_name: str = ""
    product_id: str = "cc_novichok"


ModeChoice = Literal["training", "example", "practice", "knowledge"]


@dataclass(frozen=True)
class SelectMode:
    mode: ModeChoice


@dataclass(frozen=True)
class ConfirmSkipWarning:
    accept: bool


@dataclass(frozen=True)
class TheoryDone: ...


@dataclass(frozen=True)
class SubmitQuizAnswer:
    correct: bool


@dataclass(frozen=True)
class ExplanationDone: ...


@dataclass(frozen=True)
class Continue: ...


@dataclass(frozen=True)
class ScenarioDone: ...


@dataclass(frozen=True)
class DialogDone: ...


@dataclass(frozen=True)
class PracticeEvaluated:
    weak_zones: tuple[str, ...]


@dataclass(frozen=True)
class WeakZonesSent: ...


@dataclass(frozen=True)
class ZonesDone: ...


@dataclass(frozen=True)
class RepeatCycle: ...


@dataclass(frozen=True)
class UserMessage:
    """Свободная реплика сотрудника в режиме диалога (EXAMPLE/PRACTICE/KNOWLEDGE/TRAINING).

    Не меняет FSMState — апендит реплику в ctx.dialog_history,
    SessionRunner вызывает аватар для генерации ответа по обновлённой истории.
    """

    text: str


Command = (
    StartSession
    | ResumeChoice
    | StartTraining
    | SelectMode
    | ConfirmSkipWarning
    | TheoryDone
    | SubmitQuizAnswer
    | ExplanationDone
    | Continue
    | ScenarioDone
    | DialogDone
    | PracticeEvaluated
    | WeakZonesSent
    | ZonesDone
    | RepeatCycle
    | UserMessage
)
