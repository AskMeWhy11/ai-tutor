"""FSMService: блок TRAINING (TheoryDone, SubmitQuizAnswer, ExplanationDone, Continue).

Покрывает:
* TRAINING -> TRAINING_QUIZ при TheoryDone, со сбросом quiz_question_index.
* Цикл вопросов в TRAINING_QUIZ: правильный/неправильный ответ.
* Промежуточный правильный ответ (state не меняется, индекс растёт).
* Последний правильный ответ -> TRAINING_DONE + Mode.TRAINING.
* TRAINING_EXPLAIN -> TRAINING_QUIZ при ExplanationDone (индекс не растёт).
* Continue в TRAINING_DONE -> EXAMPLE.
* Инвариант ADR-008: MAX_ATTEMPTS не эмитится.

В тестах целевое число вопросов задаётся локально через QUIZ_TARGET и
прокидывается в ``SessionContext.quiz_target_questions``. Это отражает
архитектуру после внедрения LLM-QuizDirector: число правильных ответов —
переменная контекста, а не глобальная константа.
"""

from __future__ import annotations

import dataclasses

import pytest

from application.commands import (
    Continue,
    ExplanationDone,
    SubmitQuizAnswer,
    TheoryDone,
)
from application.effects import PersistSession
from application.fsm_service import FSMService
from domain.context import SessionContext
from domain.states import FSMState, Mode

# Целевое число правильных ответов для всех тестов в этом модуле.
QUIZ_TARGET = 3


# ----------------------------------------------------------------------
# TheoryDone
# ----------------------------------------------------------------------


class TestTheoryDone:
    def test_training_to_training_quiz(self) -> None:
        service = FSMService()
        ctx = SessionContext()

        result = service.handle(FSMState.TRAINING, TheoryDone(), ctx)

        assert result.new_state is FSMState.TRAINING_QUIZ
        assert result.effects == (PersistSession(),)

    def test_resets_quiz_progress(self) -> None:
        """TheoryDone сбрасывает индекс и last_answer_correct."""
        service = FSMService()
        ctx = SessionContext(quiz_question_index=2, last_answer_correct=True)

        result = service.handle(FSMState.TRAINING, TheoryDone(), ctx)

        assert result.new_ctx.quiz_question_index == 0
        assert result.new_ctx.last_answer_correct is None

    def test_does_not_touch_other_fields(self) -> None:
        service = FSMService()
        ctx = SessionContext(
            employee_name="Анна",
            product_id="kasko",
            completed_modes=frozenset({Mode.EXAMPLE}),
            cycle_count=1,
        )

        result = service.handle(FSMState.TRAINING, TheoryDone(), ctx)

        assert result.new_ctx.employee_name == "Анна"
        assert result.new_ctx.product_id == "kasko"
        assert result.new_ctx.completed_modes == frozenset({Mode.EXAMPLE})
        assert result.new_ctx.cycle_count == 1

    def test_invalid_state(self) -> None:
        service = FSMService()
        ctx = SessionContext()

        with pytest.raises(ValueError, match="TheoryDone допустима только в TRAINING"):
            service.handle(FSMState.WELCOME, TheoryDone(), ctx)


# ----------------------------------------------------------------------
# SubmitQuizAnswer — неправильный ответ
# ----------------------------------------------------------------------


class TestSubmitQuizAnswerIncorrect:
    def test_incorrect_goes_to_training_explain(self) -> None:
        service = FSMService()
        ctx = SessionContext(quiz_question_index=0, quiz_target_questions=QUIZ_TARGET)

        result = service.handle(
            FSMState.TRAINING_QUIZ,
            SubmitQuizAnswer(correct=False),
            ctx,
        )

        assert result.new_state is FSMState.TRAINING_EXPLAIN
        assert result.effects == (PersistSession(),)

    def test_incorrect_marks_last_answer_false(self) -> None:
        service = FSMService()
        ctx = SessionContext(quiz_question_index=1, quiz_target_questions=QUIZ_TARGET)

        result = service.handle(
            FSMState.TRAINING_QUIZ,
            SubmitQuizAnswer(correct=False),
            ctx,
        )

        assert result.new_ctx.last_answer_correct is False

    def test_incorrect_does_not_advance_index(self) -> None:
        """При неверном ответе индекс не растёт: тот же вопрос будет переспрошен."""
        service = FSMService()
        ctx = SessionContext(quiz_question_index=1, quiz_target_questions=QUIZ_TARGET)

        result = service.handle(
            FSMState.TRAINING_QUIZ,
            SubmitQuizAnswer(correct=False),
            ctx,
        )

        assert result.new_ctx.quiz_question_index == 1

    def test_incorrect_does_not_complete_training(self) -> None:
        service = FSMService()
        ctx = SessionContext(
            quiz_question_index=QUIZ_TARGET - 1,
            quiz_target_questions=QUIZ_TARGET,
            completed_modes=frozenset(),
        )

        result = service.handle(
            FSMState.TRAINING_QUIZ,
            SubmitQuizAnswer(correct=False),
            ctx,
        )

        assert Mode.TRAINING not in result.new_ctx.completed_modes


# ----------------------------------------------------------------------
# SubmitQuizAnswer — правильный, не последний вопрос
# ----------------------------------------------------------------------


class TestSubmitQuizAnswerCorrectIntermediate:
    def test_state_does_not_change(self) -> None:
        """Промежуточный правильный ответ — остаёмся в TRAINING_QUIZ."""
        service = FSMService()
        ctx = SessionContext(quiz_question_index=0, quiz_target_questions=QUIZ_TARGET)

        result = service.handle(
            FSMState.TRAINING_QUIZ,
            SubmitQuizAnswer(correct=True),
            ctx,
        )

        assert result.new_state is FSMState.TRAINING_QUIZ

    def test_index_advances(self) -> None:
        service = FSMService()
        ctx = SessionContext(quiz_question_index=0, quiz_target_questions=QUIZ_TARGET)

        result = service.handle(
            FSMState.TRAINING_QUIZ,
            SubmitQuizAnswer(correct=True),
            ctx,
        )

        assert result.new_ctx.quiz_question_index == 1

    def test_marks_last_answer_true(self) -> None:
        service = FSMService()
        ctx = SessionContext(quiz_question_index=0, quiz_target_questions=QUIZ_TARGET)

        result = service.handle(
            FSMState.TRAINING_QUIZ,
            SubmitQuizAnswer(correct=True),
            ctx,
        )

        assert result.new_ctx.last_answer_correct is True

    def test_does_not_mark_training_complete(self) -> None:
        service = FSMService()
        ctx = SessionContext(
            quiz_question_index=0,
            quiz_target_questions=QUIZ_TARGET,
            completed_modes=frozenset(),
        )

        result = service.handle(
            FSMState.TRAINING_QUIZ,
            SubmitQuizAnswer(correct=True),
            ctx,
        )

        assert Mode.TRAINING not in result.new_ctx.completed_modes

    def test_persist_effect(self) -> None:
        service = FSMService()
        ctx = SessionContext(quiz_question_index=0, quiz_target_questions=QUIZ_TARGET)

        result = service.handle(
            FSMState.TRAINING_QUIZ,
            SubmitQuizAnswer(correct=True),
            ctx,
        )

        assert result.effects == (PersistSession(),)


# ----------------------------------------------------------------------
# SubmitQuizAnswer — правильный, последний вопрос
# ----------------------------------------------------------------------


class TestSubmitQuizAnswerCorrectFinal:
    def test_goes_to_training_done(self) -> None:
        service = FSMService()
        ctx = SessionContext(
            quiz_question_index=QUIZ_TARGET - 1,
            quiz_target_questions=QUIZ_TARGET,
        )

        result = service.handle(
            FSMState.TRAINING_QUIZ,
            SubmitQuizAnswer(correct=True),
            ctx,
        )

        assert result.new_state is FSMState.TRAINING_DONE

    def test_index_reaches_total(self) -> None:
        service = FSMService()
        ctx = SessionContext(
            quiz_question_index=QUIZ_TARGET - 1,
            quiz_target_questions=QUIZ_TARGET,
        )

        result = service.handle(
            FSMState.TRAINING_QUIZ,
            SubmitQuizAnswer(correct=True),
            ctx,
        )

        assert result.new_ctx.quiz_question_index == QUIZ_TARGET

    def test_marks_training_complete(self) -> None:
        service = FSMService()
        ctx = SessionContext(
            quiz_question_index=QUIZ_TARGET - 1,
            quiz_target_questions=QUIZ_TARGET,
            completed_modes=frozenset(),
        )

        result = service.handle(
            FSMState.TRAINING_QUIZ,
            SubmitQuizAnswer(correct=True),
            ctx,
        )

        assert Mode.TRAINING in result.new_ctx.completed_modes

    def test_preserves_other_completed_modes(self) -> None:
        service = FSMService()
        ctx = SessionContext(
            quiz_question_index=QUIZ_TARGET - 1,
            quiz_target_questions=QUIZ_TARGET,
            completed_modes=frozenset({Mode.EXAMPLE}),
        )

        result = service.handle(
            FSMState.TRAINING_QUIZ,
            SubmitQuizAnswer(correct=True),
            ctx,
        )

        assert result.new_ctx.completed_modes == frozenset({Mode.EXAMPLE, Mode.TRAINING})

    def test_marks_last_answer_true(self) -> None:
        service = FSMService()
        ctx = SessionContext(
            quiz_question_index=QUIZ_TARGET - 1,
            quiz_target_questions=QUIZ_TARGET,
        )

        result = service.handle(
            FSMState.TRAINING_QUIZ,
            SubmitQuizAnswer(correct=True),
            ctx,
        )

        assert result.new_ctx.last_answer_correct is True

    def test_persist_effect(self) -> None:
        service = FSMService()
        ctx = SessionContext(
            quiz_question_index=QUIZ_TARGET - 1,
            quiz_target_questions=QUIZ_TARGET,
        )

        result = service.handle(
            FSMState.TRAINING_QUIZ,
            SubmitQuizAnswer(correct=True),
            ctx,
        )

        assert result.effects == (PersistSession(),)


# ----------------------------------------------------------------------
# SubmitQuizAnswer — валидация состояния
# ----------------------------------------------------------------------


class TestSubmitQuizAnswerValidation:
    def test_invalid_state(self) -> None:
        service = FSMService()
        ctx = SessionContext()

        with pytest.raises(
            ValueError,
            match="SubmitQuizAnswer допустима только в TRAINING_QUIZ",
        ):
            service.handle(
                FSMState.TRAINING_EXPLAIN,
                SubmitQuizAnswer(correct=True),
                ctx,
            )


# ----------------------------------------------------------------------
# ExplanationDone
# ----------------------------------------------------------------------


class TestExplanationDone:
    def test_training_explain_to_training_quiz(self) -> None:
        service = FSMService()
        ctx = SessionContext(quiz_question_index=1, last_answer_correct=False)

        result = service.handle(FSMState.TRAINING_EXPLAIN, ExplanationDone(), ctx)

        assert result.new_state is FSMState.TRAINING_QUIZ
        assert result.effects == (PersistSession(),)

    def test_index_does_not_change(self) -> None:
        """После разбора отвечаем на ТОТ ЖЕ вопрос — индекс не сдвигается."""
        service = FSMService()
        ctx = SessionContext(quiz_question_index=2, last_answer_correct=False)

        result = service.handle(FSMState.TRAINING_EXPLAIN, ExplanationDone(), ctx)

        assert result.new_ctx.quiz_question_index == 2

    def test_clears_last_answer_correct(self) -> None:
        service = FSMService()
        ctx = SessionContext(quiz_question_index=1, last_answer_correct=False)

        result = service.handle(FSMState.TRAINING_EXPLAIN, ExplanationDone(), ctx)

        assert result.new_ctx.last_answer_correct is None

    def test_invalid_state(self) -> None:
        service = FSMService()
        ctx = SessionContext()

        with pytest.raises(
            ValueError,
            match="ExplanationDone допустима только в TRAINING_EXPLAIN",
        ):
            service.handle(FSMState.TRAINING_QUIZ, ExplanationDone(), ctx)


# ----------------------------------------------------------------------
# Continue в TRAINING_DONE
# ----------------------------------------------------------------------


class TestContinueFromTrainingDone:
    def test_training_done_to_example(self) -> None:
        service = FSMService()
        ctx = SessionContext(completed_modes=frozenset({Mode.TRAINING}))

        result = service.handle(FSMState.TRAINING_DONE, Continue(), ctx)

        assert result.new_state is FSMState.EXAMPLE
        assert result.new_ctx is ctx
        assert result.effects == (PersistSession(),)

    def test_continue_invalid_state(self) -> None:
        service = FSMService()
        ctx = SessionContext()

        with pytest.raises(ValueError, match="Continue допустима только"):
            service.handle(FSMState.WELCOME, Continue(), ctx)


# ----------------------------------------------------------------------
# Полный happy-path TRAINING-блока
# ----------------------------------------------------------------------


class TestTrainingHappyPath:
    """E2E внутри блока: TRAINING -> ... -> EXAMPLE через цепочку команд.

    Не использует БД и UI — только FSMService. Между шагами вручную
    подставляется ``quiz_target_questions=QUIZ_TARGET`` сразу после
    ``TheoryDone``: в проде это делает QuizDirector через
    ``SessionRunner``, когда LLM возвращает done=True.
    """

    def test_all_correct_answers_three_questions(self) -> None:
        service = FSMService()
        state = FSMState.TRAINING
        ctx = SessionContext()

        # Теория -> квиз
        result = service.handle(state, TheoryDone(), ctx)
        state, ctx = result.new_state, result.new_ctx
        assert state is FSMState.TRAINING_QUIZ
        assert ctx.quiz_question_index == 0

        # Эмулируем выбор QuizDirector: цель = 3 правильных.
        ctx = dataclasses.replace(ctx, quiz_target_questions=QUIZ_TARGET)

        # Вопрос 1 правильно
        result = service.handle(state, SubmitQuizAnswer(correct=True), ctx)
        state, ctx = result.new_state, result.new_ctx
        assert state is FSMState.TRAINING_QUIZ
        assert ctx.quiz_question_index == 1

        # Вопрос 2 правильно
        result = service.handle(state, SubmitQuizAnswer(correct=True), ctx)
        state, ctx = result.new_state, result.new_ctx
        assert state is FSMState.TRAINING_QUIZ
        assert ctx.quiz_question_index == 2

        # Вопрос 3 правильно -> TRAINING_DONE
        result = service.handle(state, SubmitQuizAnswer(correct=True), ctx)
        state, ctx = result.new_state, result.new_ctx
        assert state is FSMState.TRAINING_DONE
        assert Mode.TRAINING in ctx.completed_modes

        # Continue -> EXAMPLE
        result = service.handle(state, Continue(), ctx)
        state, ctx = result.new_state, result.new_ctx
        assert state is FSMState.EXAMPLE

    def test_one_mistake_then_recovery(self) -> None:
        """Сценарий: ошибка на вопросе 2, разбор, повторный ответ, успех."""
        service = FSMService()
        state = FSMState.TRAINING
        ctx = SessionContext()

        # Теория
        result = service.handle(state, TheoryDone(), ctx)
        state, ctx = result.new_state, result.new_ctx

        # Цель квиза — 3 правильных ответа.
        ctx = dataclasses.replace(ctx, quiz_target_questions=QUIZ_TARGET)

        # Вопрос 1 правильно
        result = service.handle(state, SubmitQuizAnswer(correct=True), ctx)
        state, ctx = result.new_state, result.new_ctx
        assert ctx.quiz_question_index == 1

        # Вопрос 2 неправильно -> EXPLAIN
        result = service.handle(state, SubmitQuizAnswer(correct=False), ctx)
        state, ctx = result.new_state, result.new_ctx
        assert state is FSMState.TRAINING_EXPLAIN
        assert ctx.quiz_question_index == 1  # индекс не сдвинулся
        assert ctx.last_answer_correct is False

        # Разбор закончен -> назад в QUIZ, тот же вопрос
        result = service.handle(state, ExplanationDone(), ctx)
        state, ctx = result.new_state, result.new_ctx
        assert state is FSMState.TRAINING_QUIZ
        assert ctx.quiz_question_index == 1
        assert ctx.last_answer_correct is None

        # Вопрос 2 повторно — правильно
        result = service.handle(state, SubmitQuizAnswer(correct=True), ctx)
        state, ctx = result.new_state, result.new_ctx
        assert ctx.quiz_question_index == 2

        # Вопрос 3 правильно -> DONE
        result = service.handle(state, SubmitQuizAnswer(correct=True), ctx)
        state, ctx = result.new_state, result.new_ctx
        assert state is FSMState.TRAINING_DONE
        assert Mode.TRAINING in ctx.completed_modes


# ----------------------------------------------------------------------
# ADR-008: MAX_ATTEMPTS не эмитится в Срезе 1
# ----------------------------------------------------------------------


class TestMaxAttemptsNotEmitted:
    """Инвариант ADR-008: ни один сценарий FSMService в Срезе 1
    не приводит к эмиссии MAX_ATTEMPTS.

    SubmitQuizAnswer при некорректном ответе всегда идёт в TRAINING_EXPLAIN,
    а не в TRAINING_DONE. Тест явно фиксирует поведение для серии ошибок.
    """

    def test_many_wrong_answers_stay_in_explain_loop(self) -> None:
        service = FSMService()
        state = FSMState.TRAINING_QUIZ
        ctx = SessionContext(quiz_question_index=0, quiz_target_questions=QUIZ_TARGET)

        for _ in range(10):
            # Неверный ответ
            result = service.handle(state, SubmitQuizAnswer(correct=False), ctx)
            assert result.new_state is FSMState.TRAINING_EXPLAIN
            state, ctx = result.new_state, result.new_ctx

            # Разбор
            result = service.handle(state, ExplanationDone(), ctx)
            assert result.new_state is FSMState.TRAINING_QUIZ
            state, ctx = result.new_state, result.new_ctx

        # Ни одного TRAINING_DONE не было — индекс не двигался.
        assert ctx.quiz_question_index == 0
        assert state is FSMState.TRAINING_QUIZ
