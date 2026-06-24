"""Инварианты контента курса КК_Новичок.

Смысл: при любой замене текстов структура остаётся валидной.
"""

from __future__ import annotations

from domain.types import ZONE_ORDER
from infrastructure.content.cc_novichok import (
    EXAMPLE_DIALOGUE,
    KNOWLEDGE_BLOCKS,
    PRACTICE_SCENARIO,
    START_MESSAGE,
    TRAINING_BLOCKS,
)


def test_start_message_is_non_empty() -> None:
    assert START_MESSAGE.strip()


def test_training_has_at_least_one_block() -> None:
    assert len(TRAINING_BLOCKS) >= 1


def test_every_training_block_has_text_question_and_keywords() -> None:
    for i, block in enumerate(TRAINING_BLOCKS):
        assert block.text.strip(), f"block {i}: empty text"
        assert block.question.strip(), f"block {i}: empty question"
        assert block.correct_answer.strip(), f"block {i}: empty correct_answer"
        assert block.keywords, f"block {i}: no keywords"
        assert all(kw.strip() for kw in block.keywords), f"block {i}: empty keyword"


def test_example_dialogue_covers_all_zones() -> None:
    assert set(EXAMPLE_DIALOGUE.keys()) == set(ZONE_ORDER)


def test_example_turns_are_filled() -> None:
    for zone, turn in EXAMPLE_DIALOGUE.items():
        assert turn.client_line.strip(), f"zone {zone}: empty client_line"
        assert turn.employee_line.strip(), f"zone {zone}: empty employee_line"
        assert turn.rationale.strip(), f"zone {zone}: empty rationale"


def test_practice_scenario_covers_all_zones() -> None:
    assert set(PRACTICE_SCENARIO.keys()) == set(ZONE_ORDER)


def test_practice_steps_are_filled() -> None:
    for zone, step in PRACTICE_SCENARIO.items():
        assert step.client_line.strip(), f"zone {zone}: empty client_line"
        assert step.keywords, f"zone {zone}: no keywords"
        assert step.feedback_ok.strip(), f"zone {zone}: empty feedback_ok"
        assert step.feedback_fail.strip(), f"zone {zone}: empty feedback_fail"


def test_knowledge_blocks_cover_all_zones() -> None:
    assert set(KNOWLEDGE_BLOCKS.keys()) == set(ZONE_ORDER)


def test_knowledge_blocks_are_non_empty() -> None:
    for _zone, text in KNOWLEDGE_BLOCKS.items():
        assert text.strip()
