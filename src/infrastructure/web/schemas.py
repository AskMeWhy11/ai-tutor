"""Pydantic-схемы HTTP API."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class StartSessionCmd(BaseModel):
    type: Literal["start_session"] = "start_session"


class ResumeChoiceCmd(BaseModel):
    type: Literal["resume_choice"] = "resume_choice"
    resume: bool


class StartTrainingCmd(BaseModel):
    type: Literal["start_training"] = "start_training"
    employee_name: str = ""
    product_id: str = "kk_novichok"


class SelectModeCmd(BaseModel):
    type: Literal["select_mode"] = "select_mode"
    mode: Literal["training", "example", "practice", "knowledge"]


class ConfirmSkipWarningCmd(BaseModel):
    type: Literal["confirm_skip_warning"] = "confirm_skip_warning"
    accept: bool


class TheoryDoneCmd(BaseModel):
    type: Literal["theory_done"] = "theory_done"


class SubmitQuizAnswerCmd(BaseModel):
    type: Literal["submit_quiz_answer"] = "submit_quiz_answer"
    correct: bool


class ExplanationDoneCmd(BaseModel):
    type: Literal["explanation_done"] = "explanation_done"


class ContinueCmd(BaseModel):
    type: Literal["continue"] = "continue"


class ScenarioDoneCmd(BaseModel):
    type: Literal["scenario_done"] = "scenario_done"


class DialogDoneCmd(BaseModel):
    type: Literal["dialog_done"] = "dialog_done"


class PracticeEvaluatedCmd(BaseModel):
    type: Literal["practice_evaluated"] = "practice_evaluated"
    weak_zones: tuple[str, ...] = ()


class WeakZonesSentCmd(BaseModel):
    type: Literal["weak_zones_sent"] = "weak_zones_sent"


class ZonesDoneCmd(BaseModel):
    type: Literal["zones_done"] = "zones_done"


class RepeatCycleCmd(BaseModel):
    type: Literal["repeat_cycle"] = "repeat_cycle"


class UserMessageCmd(BaseModel):
    type: Literal["user_message"] = "user_message"
    text: str


CommandIn = Annotated[
    StartSessionCmd
    | ResumeChoiceCmd
    | StartTrainingCmd
    | SelectModeCmd
    | ConfirmSkipWarningCmd
    | TheoryDoneCmd
    | SubmitQuizAnswerCmd
    | ExplanationDoneCmd
    | ContinueCmd
    | ScenarioDoneCmd
    | DialogDoneCmd
    | PracticeEvaluatedCmd
    | WeakZonesSentCmd
    | ZonesDoneCmd
    | RepeatCycleCmd
    | UserMessageCmd,
    Field(discriminator="type"),
]


class CommandRequest(BaseModel):
    command: CommandIn


class CtxOut(BaseModel):
    employee_name: str
    product_id: str
    completed_modes: list[str]
    weak_zones_remaining: list[str]
    cycle_count: int
    quiz_question_index: int
    last_answer_correct: bool | None
    knowledge_unlocked: bool


class AvailableCommand(BaseModel):
    type: str
    label: str
    schema_hint: dict[str, str] = Field(default_factory=dict)


class ChatMessageOut(BaseModel):
    role: Literal["user", "assistant"]
    text: str


class SessionOut(BaseModel):
    session_id: UUID
    state: str
    ctx: CtxOut
    effects: list[dict[str, str]]
    available_commands: list[AvailableCommand]
    history: list[ChatMessageOut] = Field(default_factory=list)


class CreateSessionResponse(SessionOut):
    """То же, что SessionOut."""


class CreateSessionRequest(BaseModel):
    employee_name: str = ""
    product_id: str = "kk_novichok"
    initial_mode: Literal["training", "example", "practice"] | None = None
