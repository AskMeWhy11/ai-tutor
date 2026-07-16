"""StubQuizDirector — фолбэк квиза не должен подмешивать чужой продукт."""

from __future__ import annotations

import pytest

from domain.context import SessionContext
from infrastructure.content.case_loader import invalidate_case_cache
from infrastructure.llm.stub_quiz_director import StubQuizDirector, _blocks_for_case


def setup_function() -> None:
    invalidate_case_cache()


def test_cc_novichok_uses_curated_blocks() -> None:
    blocks = _blocks_for_case("cc_novichok")
    assert blocks
    # Кураторский блок про карты ФИКС/«120 дней».
    assert any("ФИКС" in b.question or "ФИКС" in b.correct_answer for b in blocks)


def test_empty_product_falls_back_to_cc_novichok() -> None:
    assert _blocks_for_case("") == _blocks_for_case("cc_novichok")
    assert _blocks_for_case(None) == _blocks_for_case("cc_novichok")


@pytest.mark.parametrize("case_id", ["xpv", "spin", "pusk", "aida", "storytelling"])
def test_sales_technique_does_not_leak_cc_novichok_facts(case_id: str) -> None:
    blocks = _blocks_for_case(case_id)
    assert blocks, f"нет блоков для {case_id}"
    for b in blocks:
        # Никаких кредитно-карточных фактов cc_novichok в квизе техники.
        assert "карты ФИКС" not in b.question
        assert "ФИКС —" not in b.correct_answer


@pytest.mark.asyncio
async def test_stub_quiz_flow_is_product_specific() -> None:
    director = StubQuizDirector()
    ctx = SessionContext(product_id="xpv")

    kickoff = await director.next_turn(ctx, None)
    assert kickoff.verdict == "none"
    assert kickoff.next_question
    assert "ФИКС" not in kickoff.next_question

    wrong = await director.next_turn(ctx, "заведомо неверный ответ")
    assert wrong.verdict == "incorrect"
    assert "ФИКС —" not in wrong.explanation
