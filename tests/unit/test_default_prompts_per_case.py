from domain.states import Mode
from infrastructure.content.case_loader import invalidate_case_cache
from infrastructure.llm.content_render import render_prompt
from infrastructure.llm.default_prompts import default_mode_prompts


def setup_function() -> None:
    # Кейсы читаются с диска и кэшируются — сбрасываем перед каждым тестом.
    invalidate_case_cache()


def test_default_mode_prompts_are_product_agnostic() -> None:
    # PRACTICE и KNOWLEDGE универсальны и не зависят от case_id —
    # продукт/контент подставляется позже через render_prompt.
    aida = default_mode_prompts("aida")
    cc = default_mode_prompts("cc_novichok")
    assert aida[Mode.PRACTICE] == cc[Mode.PRACTICE]
    assert aida[Mode.KNOWLEDGE] == cc[Mode.KNOWLEDGE]


def test_default_example_prompt_differs_for_sales_techniques() -> None:
    # EXAMPLE для техник продаж: LLM-продавец сам ведёт клиента по всем
    # этапам техники на конкретном продукте — у cc_novichok этого нет.
    aida_example = default_mode_prompts("aida")[Mode.EXAMPLE]
    cc_example = default_mode_prompts("cc_novichok")[Mode.EXAMPLE]
    assert aida_example != cc_example
    assert "не товар, а ТЕХНИКА продажи" in aida_example
    assert "не товар, а ТЕХНИКА продажи" not in cc_example


def test_default_training_prompt_differs_for_sales_techniques() -> None:
    # TRAINING для продуктов-техник продаж требует объяснять маленькими
    # шагами кратко (2–4 предложения) и не задавать зачётных вопросов —
    # у cc_novichok этого нет.
    aida_training = default_mode_prompts("aida")[Mode.TRAINING]
    cc_training = default_mode_prompts("cc_novichok")[Mode.TRAINING]
    assert aida_training != cc_training
    assert "2–4 предложения" in aida_training
    assert "2–4 предложения" not in cc_training


def test_learning_check_is_softer_for_sales_techniques() -> None:
    # Квиз для техник продаж оценивает мягче и не требует лишнего.
    aida = default_mode_prompts("aida")[Mode.TRAINING]
    cc = default_mode_prompts("cc_novichok")[Mode.TRAINING]
    assert aida != cc
    assert "ОЦЕНИВАЙ МЯГКО" in aida
    assert "ОЦЕНИВАЙ МЯГКО" not in cc


def test_default_mode_prompts_contain_placeholders() -> None:
    prompts = default_mode_prompts()
    assert "{PRODUCT_NAME}" in prompts[Mode.TRAINING]
    assert "{PRODUCT_DETAILS}" in prompts[Mode.TRAINING]
    # Диалоговые режимы используют образцовые диалоги.
    assert "{REAL_DIALOGUES}" in prompts[Mode.EXAMPLE]
    assert "{REAL_DIALOGUES}" in prompts[Mode.PRACTICE]


def test_training_learning_check_section_placeholders() -> None:
    for cid in ("cc_novichok", "aida"):
        training = default_mode_prompts(cid)[Mode.TRAINING]
        assert "=== ЭТАП LEARNING_CHECK" in training
        assert "{STEP}" in training
        assert "{LEARNING_CHECK_LIST}" in training
        assert "{COUNT_OF_QUESTIONS}" in training


def test_default_arg_is_cc_novichok() -> None:
    assert default_mode_prompts() == default_mode_prompts("cc_novichok")


def test_cc_prompt_name_has_no_course_level_suffix() -> None:
    # «КК_Новичок» — уровень курса, а не свойство карты: в промпт он попадать
    # не должен (иначе LLM говорит «кредитная карта для новичков»), а в меню
    # метка остаётся прежней.
    from infrastructure.content.registry import case_label, case_product_name

    assert case_product_name("cc_novichok") == "Кредитная карта"
    assert "Новичок" not in case_product_name("cc_novichok")
    assert case_label("cc_novichok") == "Кредитная карта (КК_Новичок)"

    rendered = render_prompt(default_mode_prompts("cc_novichok")[Mode.TRAINING], "cc_novichok")
    assert "Новичок" not in rendered

    # У остальных продуктов название для промпта = метка.
    for cid in ("xpv", "spin", "pusk", "aida", "storytelling"):
        assert case_product_name(cid) == case_label(cid)


def test_render_makes_prompts_product_specific() -> None:
    # Универсальный шаблон → разный результат для разных продуктов.
    tpl = default_mode_prompts()[Mode.TRAINING]
    aida = render_prompt(tpl, "aida")
    cc = render_prompt(tpl, "cc_novichok")
    assert aida != cc
    assert "Техника AIDA" in aida
    assert "Кредитная карта" in cc
    # Плейсхолдеры в результате не остаются.
    assert "{PRODUCT_NAME}" not in aida
    assert "{PRODUCT_DETAILS}" not in aida
