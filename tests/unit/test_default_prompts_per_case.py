from domain.states import Mode
from infrastructure.content.case_loader import invalidate_case_cache
from infrastructure.llm.default_prompts import default_mode_prompts, default_quiz_prompt


def setup_function() -> None:
    # Кейсы читаются с диска и кэшируются — сбрасываем перед каждым тестом.
    invalidate_case_cache()


def test_mode_prompts_use_case_facts() -> None:
    aida = default_mode_prompts("aida")
    cc = default_mode_prompts("cc_novichok")
    # Контент AIDA отличается от дефолтной кредитки.
    assert aida[Mode.TRAINING] != cc[Mode.TRAINING]
    # И содержит маркеры техники AIDA.
    assert "AIDA" in aida[Mode.TRAINING] or "Attention" in aida[Mode.TRAINING]


def test_quiz_prompt_per_case() -> None:
    assert default_quiz_prompt("aida") != default_quiz_prompt("cc_novichok")


def test_default_arg_is_cc_novichok() -> None:
    assert default_mode_prompts() == default_mode_prompts("cc_novichok")
