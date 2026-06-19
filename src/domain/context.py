"""Контекст сессии обучения.

Хранит факты прохождения и историю реплик активного режима.
Мутируется только в FSMService через dataclasses.replace.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from domain.constants import TRAINING_QUIZ_QUESTIONS
from domain.states import FSMState, Mode
from domain.types import ChatMessage


@dataclass(frozen=True)
class SessionContext:
    has_active_session: bool = False
    employee_name: str = ""
    product_id: str = ""
    completed_modes: frozenset[Mode] = frozenset()
    weak_zones_remaining: tuple[str, ...] = ()
    cycle_count: int = 0
    quiz_question_index: int = 0
    last_answer_correct: bool | None = None
    saved_state: FSMState | None = None

    # Целевое количество правильных ответов в TRAINING_QUIZ.
    # По умолчанию — константа TRAINING_QUIZ_QUESTIONS, но QuizDirector
    # может уменьшить значение до (quiz_question_index + 1), чтобы LLM
    # самостоятельно завершила квиз раньше срока. См. ADR-013 (TBD).
    quiz_target_questions: int = TRAINING_QUIZ_QUESTIONS

    # История диалога текущего режима. Сбрасывается при входе в новый режим.
    dialog_history: tuple[ChatMessage, ...] = field(default_factory=tuple)

    @property
    def knowledge_unlocked(self) -> bool:
        return Mode.PRACTICE in self.completed_modes and bool(self.weak_zones_remaining)
