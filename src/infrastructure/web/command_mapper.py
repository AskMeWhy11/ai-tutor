"""Маппинг Pydantic-команд → dataclass-команды + список доступных команд по state."""

from __future__ import annotations

from application.commands import (
    Command,
    ConfirmSkipWarning,
    Continue,
    DialogDone,
    ExplanationDone,
    PracticeEvaluated,
    RepeatCycle,
    ResumeChoice,
    ScenarioDone,
    SelectMode,
    StartSession,
    StartTraining,
    SubmitQuizAnswer,
    TheoryDone,
    UserMessage,
    WeakZonesSent,
    ZonesDone,
)
from domain.states import FSMState
from infrastructure.web.schemas import (
    AvailableCommand,
    CommandIn,
    ConfirmSkipWarningCmd,
    ContinueCmd,
    DialogDoneCmd,
    ExplanationDoneCmd,
    PracticeEvaluatedCmd,
    RepeatCycleCmd,
    ResumeChoiceCmd,
    ScenarioDoneCmd,
    SelectModeCmd,
    StartSessionCmd,
    StartTrainingCmd,
    SubmitQuizAnswerCmd,
    TheoryDoneCmd,
    UserMessageCmd,
    WeakZonesSentCmd,
    ZonesDoneCmd,
)


def to_domain_command(cmd: CommandIn) -> Command:
    if isinstance(cmd, StartSessionCmd):
        return StartSession()
    if isinstance(cmd, ResumeChoiceCmd):
        return ResumeChoice(resume=cmd.resume)
    if isinstance(cmd, StartTrainingCmd):
        return StartTraining(employee_name=cmd.employee_name, product_id=cmd.product_id)
    if isinstance(cmd, SelectModeCmd):
        return SelectMode(mode=cmd.mode)
    if isinstance(cmd, ConfirmSkipWarningCmd):
        return ConfirmSkipWarning(accept=cmd.accept)
    if isinstance(cmd, TheoryDoneCmd):
        return TheoryDone()
    if isinstance(cmd, SubmitQuizAnswerCmd):
        return SubmitQuizAnswer(correct=cmd.correct)
    if isinstance(cmd, ExplanationDoneCmd):
        return ExplanationDone()
    if isinstance(cmd, ContinueCmd):
        return Continue()
    if isinstance(cmd, ScenarioDoneCmd):
        return ScenarioDone()
    if isinstance(cmd, DialogDoneCmd):
        return DialogDone()
    if isinstance(cmd, PracticeEvaluatedCmd):
        return PracticeEvaluated(weak_zones=cmd.weak_zones)
    if isinstance(cmd, WeakZonesSentCmd):
        return WeakZonesSent()
    if isinstance(cmd, ZonesDoneCmd):
        return ZonesDone()
    if isinstance(cmd, RepeatCycleCmd):
        return RepeatCycle()
    if isinstance(cmd, UserMessageCmd):
        return UserMessage(text=cmd.text)
    raise ValueError(f"Неизвестная команда: {cmd!r}")


_RESUME = AvailableCommand(
    type="resume_choice",
    label="Продолжить или начать заново",
    schema_hint={"resume": "bool"},
)
_START_TRAINING = AvailableCommand(
    type="start_training",
    label="Начать обучение",
    schema_hint={"employee_name": "str", "product_id": "str"},
)
_SELECT_MODE = AvailableCommand(
    type="select_mode",
    label="Выбрать режим",
    schema_hint={"mode": "training|example|practice|knowledge"},
)
_CONFIRM_SKIP = AvailableCommand(
    type="confirm_skip_warning",
    label="Подтвердить пропуск",
    schema_hint={"accept": "bool"},
)
_USER_MESSAGE = AvailableCommand(
    type="user_message",
    label="Свободная реплика",
    schema_hint={"text": "str"},
)


# В стадийных состояниях оставляем ТОЛЬКО user_message — стадией управляет
# StageDirector, и пользователь не должен видеть кнопок «Я закончил».
# Технические состояния (DONE/PARTIAL/SUCCESS) тоже не требуют user-action:
# SessionRunner авто-эмитит Continue / WeakZonesSent / RepeatCycle.
_AVAILABLE: dict[FSMState, tuple[AvailableCommand, ...]] = {
    FSMState.INIT: (AvailableCommand(type="start_session", label="Старт"),),
    FSMState.RESUME_PROMPT: (_RESUME,),
    FSMState.MENU: (_START_TRAINING,),
    FSMState.WELCOME: (_SELECT_MODE,),
    FSMState.SKIP_WARNING_1: (_CONFIRM_SKIP,),
    FSMState.SKIP_WARNING_2: (_CONFIRM_SKIP,),
    FSMState.TRAINING: (_USER_MESSAGE,),
    FSMState.TRAINING_QUIZ: (_USER_MESSAGE,),
    FSMState.TRAINING_EXPLAIN: (),  # авто-проходим в session_runner
    FSMState.TRAINING_DONE: (),  # авто-CONTINUE
    FSMState.EXAMPLE: (_USER_MESSAGE,),
    FSMState.EXAMPLE_DONE: (),  # авто-CONTINUE
    FSMState.PRACTICE: (_USER_MESSAGE,),
    FSMState.PRACTICE_EVAL: (),  # авто-PracticeEvaluated
    FSMState.PRACTICE_PARTIAL: (),  # авто-WeakZonesSent
    FSMState.PRACTICE_SUCCESS: (),  # авто-CONTINUE
    FSMState.KNOWLEDGE: (_USER_MESSAGE,),
    FSMState.KNOWLEDGE_DONE: (),  # авто-RepeatCycle
    FSMState.FINISH: (),
}


def available_commands_for(state: FSMState) -> list[AvailableCommand]:
    return list(_AVAILABLE.get(state, ()))
