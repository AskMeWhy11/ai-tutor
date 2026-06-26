from domain.states import Mode
from infrastructure.content.case_loader import invalidate_case_cache
from infrastructure.llm.content_render import render_prompt
from infrastructure.llm.default_prompts import default_mode_prompts, default_quiz_prompt


def setup_function() -> None:
    # Кейсы читаются с диска и кэшируются — сбрасываем перед каждым тестом.
    invalidate_case_cache()


def test_default_mode_prompts_are_product_agnostic() -> None:
    # Дефолтные шаблоны универсальны и не зависят от case_id —
    # продукт/контент подставляется позже через render_prompt.
    assert default_mode_prompts("aida") == default_mode_prompts("cc_novichok")


def test_default_mode_prompts_contain_placeholders() -> None:
    prompts = default_mode_prompts()
    assert "{PRODUCT}" in prompts[Mode.TRAINING]
    assert "{FACTS}" in prompts[Mode.TRAINING]
    # Диалоговые режимы используют образцовые диалоги.
    assert "{DIALOGUES}" in prompts[Mode.EXAMPLE]
    assert "{DIALOGUES}" in prompts[Mode.PRACTICE]


def test_default_quiz_prompt_is_product_agnostic() -> None:
    assert default_quiz_prompt("aida") == default_quiz_prompt("cc_novichok")
    assert "{PRODUCT}" in default_quiz_prompt()
    assert "{FACTS}" in default_quiz_prompt()


def test_default_arg_is_cc_novichok() -> None:
    assert default_mode_prompts() == default_mode_prompts("cc_novichok")


def test_render_makes_prompts_product_specific() -> None:
    # Универсальный шаблон → разный результат для разных продуктов.
    tpl = default_mode_prompts()[Mode.TRAINING]
    aida = render_prompt(tpl, "aida")
    cc = render_prompt(tpl, "cc_novichok")
    assert aida != cc
    assert "Техника AIDA" in aida
    assert "Кредитная карта" in cc
    # Плейсхолдеры в результате не остаются.
    assert "{PRODUCT}" not in aida
    assert "{FACTS}" not in aida
