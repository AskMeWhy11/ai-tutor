"""StubAnswerChecker — позитивы и негативы по training-методу + legacy practice."""

from __future__ import annotations

import pytest

from infrastructure.llm.stub_checker import StubAnswerChecker


@pytest.fixture
def checker() -> StubAnswerChecker:
    return StubAnswerChecker()


# ---------- TRAINING (async, CheckResult) ----------


@pytest.mark.asyncio
async def test_training_accepts_answer_with_keyword(checker: StubAnswerChecker) -> None:
    res = await checker.check_training_answer(0, "ФИКС — для наличных, а 120 дней для покупок")
    assert res.correct is True


@pytest.mark.asyncio
async def test_training_rejects_irrelevant_answer(checker: StubAnswerChecker) -> None:
    res = await checker.check_training_answer(0, "не знаю, не помню")
    assert res.correct is False


@pytest.mark.asyncio
async def test_training_is_case_insensitive(checker: StubAnswerChecker) -> None:
    assert (await checker.check_training_answer(0, "ФИКС")).correct
    assert (await checker.check_training_answer(0, "фикс")).correct


@pytest.mark.asyncio
async def test_training_rejects_out_of_range_index(checker: StubAnswerChecker) -> None:
    res = await checker.check_training_answer(999, "ФИКС наличные")
    assert res.correct is False


@pytest.mark.asyncio
async def test_training_rejects_empty_text(checker: StubAnswerChecker) -> None:
    res = await checker.check_training_answer(0, "")
    assert res.correct is False


# ---------- PRACTICE (legacy sync API, оставлено для обратной совместимости) ----------


def test_practice_accepts_correct_pitch(checker: StubAnswerChecker) -> None:
    assert checker.evaluate_practice(
        "pitch", "Предлагаю карту ФИКС, до 50 тысяч в месяц без комиссии"
    )


def test_practice_rejects_wrong_product_in_pitch(checker: StubAnswerChecker) -> None:
    assert not checker.evaluate_practice("pitch", "оформим вам 120 дней, отличный продукт")


def test_practice_accepts_needs_clarification(checker: StubAnswerChecker) -> None:
    assert checker.evaluate_practice("needs", "А вам наличные нужны или картой удобнее?")


def test_practice_accepts_conditions_explanation(checker: StubAnswerChecker) -> None:
    assert checker.evaluate_practice(
        "conditions", "Если вернёте до конца месяца — бесплатно, никаких процентов"
    )


def test_practice_rejects_unknown_zone(checker: StubAnswerChecker) -> None:
    assert not checker.evaluate_practice("nonsense", "что-то")  # type: ignore[arg-type]
